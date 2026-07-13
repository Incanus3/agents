import os
import shutil
import stat
import sys

from .errors import OperationalError
from .layout import (
    canonical_alias,
    lexists,
    real_kind,
    set_path,
    validate_layout,
    validate_lockfile,
    validate_name,
    validate_set,
    write_empty_lock,
)


def preflight_init(root, name):
    validate_name(name)
    for managed in (
        root / "skillsets",
        root / "active",
        root / ".skillset-use.staging",
    ):
        if lexists(managed):
            raise OperationalError(f"partial or existing managed layout found at {managed}")
    skills = root / "skills"
    lockfile = root / ".skill-lock.json"
    if lexists(skills) and not real_kind(skills, stat.S_ISDIR):
        raise OperationalError(f"existing skills must be a real directory: {skills}")
    if lexists(lockfile):
        validate_lockfile(lockfile)
    return lexists(skills), lexists(lockfile)


def cleanup_init_aliases(aliases):
    problems = []
    for alias, expected_target in reversed(aliases):
        try:
            if alias.is_symlink() and os.readlink(alias) == expected_target:
                alias.unlink()
            elif lexists(alias):
                raise OSError(f"unexpected entry blocks rollback at {alias}")
        except Exception as error:
            problems.append(f"could not remove {alias}: {error}")
    return problems


def restore_init_contents(root, target, had_skills, had_lock):
    problems = []
    pairs = (
        (had_skills, target / "skills", root / "skills", "directory"),
        (had_lock, target / ".skill-lock.json", root / ".skill-lock.json", "file"),
    )
    for existed, staged, original, kind in pairs:
        try:
            if existed:
                if not lexists(original) and lexists(staged):
                    shutil.move(os.fspath(staged), os.fspath(original))
                elif not lexists(original):
                    raise OSError(f"both original and staged {kind} are missing")
                elif lexists(staged):
                    raise OSError(f"both original and staged {kind} exist")
            elif lexists(staged):
                if kind == "directory":
                    shutil.rmtree(staged)
                else:
                    staged.unlink()
        except Exception as error:
            problems.append(f"could not restore {original}: {error}")
    return problems


def rollback_init(root, target, had_skills, had_lock, aliases):
    problems = cleanup_init_aliases(aliases)
    problems.extend(restore_init_contents(root, target, had_skills, had_lock))

    for directory in (target, root / "skillsets"):
        try:
            if lexists(directory):
                directory.rmdir()
        except Exception as error:
            problems.append(f"could not remove {directory}: {error}")
    return problems


def materialize_initial_set(root, target, had_skills, had_lock):
    target.parent.mkdir()
    target.mkdir()
    if had_skills:
        shutil.move(os.fspath(root / "skills"), os.fspath(target / "skills"))
    else:
        (target / "skills").mkdir()
    if had_lock:
        shutil.move(
            os.fspath(root / ".skill-lock.json"),
            os.fspath(target / ".skill-lock.json"),
        )
    else:
        write_empty_lock(target / ".skill-lock.json")


def init(root, name):
    had_skills, had_lock = preflight_init(root, name)
    target = set_path(root, name)
    aliases = []
    try:
        materialize_initial_set(root, target, had_skills, had_lock)
        for path, link_target in (
            (root / "active", f"skillsets/{name}"),
            (root / "skills", "active/skills"),
            (root / ".skill-lock.json", "active/.skill-lock.json"),
        ):
            aliases.append((path, link_target))
            os.symlink(link_target, path)
    except (Exception, KeyboardInterrupt) as error:
        rollback_problems = rollback_init(root, target, had_skills, had_lock, aliases)
        if rollback_problems:
            details = "; ".join(rollback_problems)
            raise OperationalError(
                f"initialization failed ({error}); rollback was incomplete ({details}). "
                f"Inspect original paths {root / 'skills'} and "
                f"{root / '.skill-lock.json'} plus staged set {target}; "
                "preserve the only remaining copy of any data, run `skillset doctor`, "
                "and restore any missing original only from its staged counterpart."
            ) from error
        if isinstance(error, KeyboardInterrupt):
            raise
        raise OperationalError(f"initialization failed and was rolled back: {error}") from error


def populate_staged_set(staging, source_path):
    if source_path is None:
        (staging / "skills").mkdir()
        write_empty_lock(staging / ".skill-lock.json")
        return
    shutil.copytree(
        source_path / "skills",
        staging / "skills",
        symlinks=True,
        copy_function=shutil.copy2,
    )
    shutil.copy2(source_path / ".skill-lock.json", staging / ".skill-lock.json")


def create(root, name, source):
    validate_name(name)
    if source is not None:
        validate_name(source)
    validate_layout(root)
    destination = set_path(root, name)
    staging = root / "skillsets" / f".skillset-create-{name}.staging"
    if lexists(destination):
        raise OperationalError(f"skillset already exists: {destination}")
    if lexists(staging):
        raise OperationalError(f"stale create staging path must be recovered: {staging}")
    source_path = validate_set(root, source) if source is not None else None
    try:
        staging.mkdir()
        populate_staged_set(staging, source_path)
        if lexists(destination):
            raise OperationalError(f"skillset appeared during creation: {destination}")
        os.rename(staging, destination)
    except OperationalError:
        raise
    except Exception as error:
        raise OperationalError(
            f"could not create {name!r}; staging was retained at {staging}: {error}"
        ) from error


def use(root, name):
    validate_name(name)
    validate_layout(root)
    validate_set(root, name)
    active = root / "active"
    staging = root / ".skillset-use.staging"
    if lexists(staging):
        raise OperationalError(f"stale use staging path must be recovered: {staging}")
    try:
        os.symlink(f"skillsets/{name}", staging)
        os.replace(staging, active)
    except Exception as error:
        try:
            if lexists(staging):
                staging.unlink()
        except OSError:
            pass
        raise OperationalError(f"could not activate {name!r}: {error}") from error


def cleanup_rename_staging(staging, target):
    if not lexists(staging):
        return None
    if not canonical_alias(staging, target):
        return f"refused to remove noncanonical staging path {staging}"
    try:
        staging.unlink()
    except (Exception, KeyboardInterrupt) as error:
        if lexists(staging):
            return f"could not remove canonical staging symlink {staging}: {error}"
    return None


def set_is_valid(root, name):
    try:
        validate_set(root, name)
    except OperationalError:
        return False
    return True


def active_rename_committed(root, new_name, active, new_target):
    return canonical_alias(active, new_target) and set_is_valid(root, new_name)


def rollback_active_rename_directory(
    root, old_name, new_name, old, new, active, old_target, staging
):
    if not canonical_alias(active, old_target):
        return False, [f"active alias is not canonical for {old} or {new}: {active}"]

    problems = []
    if not lexists(old) and set_is_valid(root, new_name):
        try:
            os.rename(new, old)
        except (Exception, KeyboardInterrupt) as rollback_error:
            problems.append(f"could not roll back {new} to {old}: {rollback_error}")
    elif not (set_is_valid(root, old_name) and not lexists(new)):
        problems.append(f"could not safely roll back {new} to {old}")

    rolled_back = (
        canonical_alias(active, old_target)
        and set_is_valid(root, old_name)
        and not lexists(new)
        and not lexists(staging)
    )
    return rolled_back, problems


def incomplete_active_rename(error, old, new, active, problems):
    details = "; ".join(problems)
    remaining = [str(path) for path in (old, new) if lexists(path)]
    location = ", ".join(remaining) if remaining else "neither expected set path"
    raise OperationalError(
        f"active rename failed ({error}); recovery could not restore a valid "
        f"layout ({details}). Remaining set data is at {location}. Preserve it; "
        f"inspect {old}, {new}, and {active} before moving the set back or "
        "retargeting active, then run `skillset doctor`."
    ) from error


def recover_active_rename(root, old_name, new_name, error):
    old = set_path(root, old_name)
    new = set_path(root, new_name)
    active = root / "active"
    staging = root / ".skillset-use.staging"
    old_target = f"skillsets/{old_name}"
    new_target = f"skillsets/{new_name}"
    cleanup_problem = cleanup_rename_staging(staging, new_target)

    if active_rename_committed(root, new_name, active, new_target):
        if cleanup_problem is not None:
            incomplete_active_rename(
                error, old, new, active, [cleanup_problem]
            )
        if isinstance(error, KeyboardInterrupt):
            raise error
        return

    rolled_back, problems = rollback_active_rename_directory(
        root, old_name, new_name, old, new, active, old_target, staging
    )
    if cleanup_problem is not None:
        problems.insert(0, cleanup_problem)
    if rolled_back:
        if isinstance(error, KeyboardInterrupt):
            raise error
        raise OperationalError(
            f"could not rename active skillset {old_name!r} to {new_name!r}; "
            f"the directory rename was rolled back: {error}"
        ) from error

    if not problems:
        problems.append("rollback did not restore the original layout")
    incomplete_active_rename(error, old, new, active, problems)


def rename_inactive_set(old, new, old_name, new_name):
    try:
        os.rename(old, new)
    except Exception as error:
        raise OperationalError(
            f"could not rename {old_name!r} to {new_name!r}: {error}"
        ) from error


def rename_active_set(root, old, new, old_name, new_name):
    staging = root / ".skillset-use.staging"
    if lexists(staging):
        raise OperationalError(f"stale use staging path must be recovered: {staging}")
    try:
        os.rename(old, new)
    except (Exception, KeyboardInterrupt) as error:
        recover_active_rename(root, old_name, new_name, error)
        return
    try:
        os.symlink(f"skillsets/{new_name}", staging)
        os.replace(staging, root / "active")
    except (Exception, KeyboardInterrupt) as error:
        recover_active_rename(root, old_name, new_name, error)


def rename(root, old_name, new_name):
    validate_name(old_name)
    validate_name(new_name)
    active_name = validate_layout(root)
    old = validate_set(root, old_name)
    new = set_path(root, new_name)
    if lexists(new):
        raise OperationalError(f"skillset already exists: {new}")

    if old_name != active_name:
        rename_inactive_set(old, new, old_name, new_name)
        return

    rename_active_set(root, old, new, old_name, new_name)


def confirm_removal(name):
    print(
        f"Remove skillset {name!r}? [y/N] ",
        end="",
        file=sys.stderr,
        flush=True,
    )
    if sys.stdin.readline().strip().lower() not in {"y", "yes"}:
        raise OperationalError(f"removal of skillset {name!r} cancelled")


def remove(root, name, confirmed):
    validate_name(name)
    active_name = validate_layout(root)
    target = validate_set(root, name)
    if name == active_name:
        raise OperationalError(
            f"cannot remove active skillset {name!r}; activate another set first"
        )
    if not confirmed:
        confirm_removal(name)
    try:
        shutil.rmtree(target)
    except Exception as error:
        raise OperationalError(f"could not remove skillset {name!r}: {error}") from error
