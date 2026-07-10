import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager

from .errors import OperationalError


EMPTY_LOCK = {"version": 3, "skills": {}, "dismissed": {}}
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


def lexists(path):
    return os.path.lexists(path)


def real_kind(path, expected):
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    if stat.S_ISLNK(mode):
        return False
    return expected(mode)


def validate_name(name):
    if not NAME_PATTERN.fullmatch(name):
        raise OperationalError(
            f"invalid skillset name {name!r}; use lowercase letters, digits, '_' or '-'"
        )


def set_path(root, name):
    validate_name(name)
    path = root / "skillsets" / name
    if path.parent != root / "skillsets":
        raise OperationalError(f"unsafe skillset path for {name!r}")
    return path


def read_lockfile(path):
    if not real_kind(path, stat.S_ISREG):
        raise OperationalError(f"lockfile must be a real regular file: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OperationalError(f"invalid lockfile {path}: {error}") from error
    valid = (
        isinstance(value, dict)
        and type(value.get("version")) is int
        and value.get("version") == 3
        and isinstance(value.get("skills"), dict)
        and isinstance(value.get("dismissed"), dict)
    )
    if not valid:
        raise OperationalError(f"lockfile is not a version-3 global lockfile: {path}")
    return value


def validate_lockfile(path):
    read_lockfile(path)


def validate_set(root, name):
    path = set_path(root, name)
    if not real_kind(path, stat.S_ISDIR):
        raise OperationalError(f"skillset must be a real directory: {path}")
    skills = path / "skills"
    if not real_kind(skills, stat.S_ISDIR):
        raise OperationalError(f"skills must be a real directory: {skills}")
    validate_lockfile(path / ".skill-lock.json")
    return path


def require_alias(path, target):
    if not path.is_symlink() or os.readlink(path) != target:
        raise OperationalError(f"managed alias must be {path} -> {target}")


def canonical_alias(path, target):
    try:
        return path.is_symlink() and os.readlink(path) == target
    except OSError:
        return False


def validate_layout(root):
    skillsets = root / "skillsets"
    if not real_kind(skillsets, stat.S_ISDIR):
        raise OperationalError("skillsets are not initialized")
    use_staging = root / ".skillset-use.staging"
    if lexists(use_staging):
        raise OperationalError(
            f"stale active staging path must be recovered: {use_staging}"
        )
    require_alias(root / "skills", "active/skills")
    require_alias(root / ".skill-lock.json", "active/.skill-lock.json")
    active = root / "active"
    if not active.is_symlink():
        raise OperationalError(f"managed alias is missing or invalid: {active}")
    target = os.readlink(active)
    if not target.startswith("skillsets/"):
        raise OperationalError(f"active alias has a noncanonical target: {target}")
    active_name = target[len("skillsets/") :]
    validate_name(active_name)
    if target != f"skillsets/{active_name}":
        raise OperationalError(f"active alias has a noncanonical target: {target}")
    validate_set(root, active_name)
    for entry in skillsets.iterdir():
        if entry.name.startswith(".skillset-create-") and entry.name.endswith(
            ".staging"
        ):
            raise OperationalError(
                f"stale create staging path must be recovered: {entry}"
            )
        validate_name(entry.name)
        validate_set(root, entry.name)
    return active_name


@contextmanager
def stable_home_lock(root):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = os.open(root.parent, flags)
    except OSError as error:
        raise OperationalError(
            f"HOME must be an existing real directory: {root.parent}: {error}"
        ) from error
    locked = False
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield descriptor
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def operation_lock(root, create=True):
    if lexists(root) and not real_kind(root, stat.S_ISDIR):
        raise OperationalError(f"managed root must be a real directory: {root}")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    elif not real_kind(root, stat.S_ISDIR):
        raise OperationalError(f"managed root must be a real directory: {root}")
    lock_path = root / ".skillset.lock"
    if not create and not real_kind(lock_path, stat.S_ISREG):
        raise OperationalError(f"advisory lock must be a real file: {lock_path}")
    if lexists(lock_path) and not real_kind(lock_path, stat.S_ISREG):
        raise OperationalError(f"advisory lock must be a real file: {lock_path}")
    mode = "a+" if create else "r"
    with lock_path.open(mode) as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield lock_file
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


@contextmanager
def doctor_operation_lock(root, errors):
    lock_path = root / ".skillset.lock"
    try:
        metadata = lock_path.lstat()
    except FileNotFoundError:
        errors.append(f"advisory lock is missing: {lock_path}")
        yield None
        return
    except OSError as error:
        errors.append(f"could not inspect advisory lock {lock_path}: {error}")
        yield None
        return
    if stat.S_ISLNK(metadata.st_mode):
        errors.append(f"advisory lock symlink is not allowed: {lock_path}")
        yield None
        return
    if not stat.S_ISREG(metadata.st_mode):
        errors.append(f"advisory lock must be a real regular file: {lock_path}")
        yield None
        return

    try:
        descriptor = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as error:
        errors.append(f"could not open advisory lock {lock_path}: {error}")
        yield None
        return
    locked = False
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (metadata.st_dev, metadata.st_ino):
            errors.append(f"advisory lock changed during inspection: {lock_path}")
            yield None
            return
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield descriptor
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def write_empty_lock(path):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(EMPTY_LOCK, handle)
        handle.write("\n")
