import os
import stat
import sys

from .errors import OperationalError
from .layout import NAME_PATTERN, doctor_operation_lock, lexists, read_lockfile
from .metadata import parse_frontmatter, printable_text, read_skill_text


def doctor_alias(path, target, errors):
    if not lexists(path):
        errors.append(f"managed alias is missing: {path}")
        return
    if not path.is_symlink():
        errors.append(f"managed alias must be a symlink: {path} -> {target}")
        return
    try:
        actual = os.readlink(path)
    except OSError as error:
        errors.append(f"could not read managed alias {path}: {error}")
        return
    if actual != target:
        errors.append(
            f"managed alias is noncanonical: {path} -> {actual}; expected {target}"
        )


def doctor_lockfile(path, errors):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        errors.append(f"lockfile is missing: {path}")
        return None
    except OSError as error:
        errors.append(f"could not inspect lockfile {path}: {error}")
        return None
    if stat.S_ISLNK(mode):
        errors.append(f"lockfile symlink is not allowed: {path}")
        return None
    if not stat.S_ISREG(mode):
        errors.append(f"lockfile must be a real regular file: {path}")
        return None
    try:
        return read_lockfile(path)
    except OperationalError as error:
        errors.append(str(error))
        return None
    except Exception as error:
        errors.append(f"could not read lockfile {path}: {error}")
        return None


def doctor_skills(skills, set_name, errors):
    installed = set()
    try:
        candidates = sorted(skills.iterdir(), key=lambda path: path.name)
    except OSError as error:
        errors.append(f"could not inspect skills directory {skills}: {error}")
        return None
    for candidate in candidates:
        try:
            mode = candidate.lstat().st_mode
        except OSError as error:
            errors.append(f"could not inspect skill {candidate}: {error}")
            continue
        if stat.S_ISREG(mode):
            continue
        if stat.S_ISLNK(mode):
            errors.append(
                f"skill directory symlink is not allowed in {set_name!r}: {candidate}"
            )
            continue
        if not stat.S_ISDIR(mode):
            errors.append(f"unsupported skill entry type in {set_name!r}: {candidate}")
            continue
        installed.add(candidate.name)
        try:
            text, reason = read_skill_text(candidate)
            if reason is None:
                _metadata, reason = parse_frontmatter(text)
        except Exception as error:
            errors.append(f"could not inspect skill metadata {candidate}: {error}")
            continue
        if reason is not None:
            errors.append(f"invalid skill metadata in {set_name!r}/{candidate.name}: {reason}")
    return installed


def doctor_skills_directory(path, name, errors):
    skills = path / "skills"
    try:
        skills_mode = skills.lstat().st_mode
    except FileNotFoundError:
        errors.append(f"skills directory is missing: {skills}")
    except OSError as error:
        errors.append(f"could not inspect skills directory {skills}: {error}")
    else:
        if stat.S_ISLNK(skills_mode):
            errors.append(f"skills directory symlink is not allowed: {skills}")
        elif not stat.S_ISDIR(skills_mode):
            errors.append(f"skills must be a real directory: {skills}")
        else:
            return doctor_skills(skills, name, errors)
    return None


def doctor_skill_inventory(name, installed, lock, warnings):
    locked = set(lock["skills"])
    for skill_name in sorted(installed - locked):
        warnings.append(
            f"installed skill directory {skill_name!r} in {name!r} is missing from the lockfile"
        )
    for skill_name in sorted(locked - installed):
        warnings.append(
            f"lockfile skill {skill_name!r} in {name!r} has no real direct skill directory"
        )


def doctor_set(path, name, errors, warnings):
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        errors.append(f"could not inspect skillset {name!r} at {path}: {error}")
        return
    if stat.S_ISLNK(mode):
        errors.append(f"skillset directory symlink is not allowed: {path}")
        return
    if not stat.S_ISDIR(mode):
        errors.append(f"skillset must be a real directory: {path}")
        return

    installed = doctor_skills_directory(path, name, errors)
    lock = doctor_lockfile(path / ".skill-lock.json", errors)
    if installed is None or lock is None:
        return
    doctor_skill_inventory(name, installed, lock, warnings)


def doctor_skillsets_directory(skillsets, errors):
    try:
        skillsets_mode = skillsets.lstat().st_mode
    except FileNotFoundError:
        errors.append(f"skillsets directory is missing: {skillsets}")
    except OSError as error:
        errors.append(f"could not inspect skillsets directory {skillsets}: {error}")
    else:
        if stat.S_ISLNK(skillsets_mode):
            errors.append(f"skillsets directory symlink is not allowed: {skillsets}")
        elif not stat.S_ISDIR(skillsets_mode):
            errors.append(f"skillsets must be a real directory: {skillsets}")
        else:
            return True
    return False


def doctor_active_alias(active, skillsets, skillsets_valid, errors):
    if not lexists(active):
        errors.append(f"managed active alias is missing: {active}")
    elif not active.is_symlink():
        errors.append(f"managed active alias must be a symlink: {active}")
    else:
        try:
            target = os.readlink(active)
        except OSError as error:
            errors.append(f"could not read managed active alias {active}: {error}")
        else:
            prefix = "skillsets/"
            candidate = target[len(prefix) :] if target.startswith(prefix) else ""
            if not NAME_PATTERN.fullmatch(candidate) or target != prefix + candidate:
                errors.append(
                    f"active alias has a noncanonical target; expected skillsets/NAME: {target}"
                )
            elif skillsets_valid and not lexists(skillsets / candidate):
                errors.append(f"active target is missing: {active} -> {target}")


def doctor_skillset_entries(skillsets, errors, warnings):
    try:
        entries = sorted(skillsets.iterdir(), key=lambda path: path.name)
    except OSError as error:
        errors.append(f"could not inspect skillsets directory {skillsets}: {error}")
        return
    for entry in entries:
        if entry.name.startswith(".skillset-create-") and entry.name.endswith(
            ".staging"
        ):
            errors.append(f"stale create staging path must be recovered: {entry}")
            continue
        if not NAME_PATTERN.fullmatch(entry.name):
            errors.append(
                f"invalid skillset name {entry.name!r} at {entry}; "
                "use lowercase letters, digits, '_' or '-'"
            )
        doctor_set(entry, entry.name, errors, warnings)


def doctor_inspection(root, errors, warnings):
    skillsets = root / "skillsets"
    skillsets_valid = doctor_skillsets_directory(skillsets, errors)

    doctor_alias(root / "skills", "active/skills", errors)
    doctor_alias(root / ".skill-lock.json", "active/.skill-lock.json", errors)
    doctor_active_alias(root / "active", skillsets, skillsets_valid, errors)

    use_staging = root / ".skillset-use.staging"
    if lexists(use_staging):
        errors.append(f"stale active staging path must be recovered: {use_staging}")

    if skillsets_valid:
        doctor_skillset_entries(skillsets, errors, warnings)


def doctor(root):
    errors = []
    warnings = []
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError:
        root_mode = None
    except OSError as error:
        errors.append(f"could not inspect managed root {root}: {error}")
        root_mode = False
    if root_mode is not None and (
        root_mode is False
        or stat.S_ISLNK(root_mode)
        or not stat.S_ISDIR(root_mode)
    ):
        if root_mode is not False:
            errors.append(f"managed root must be a real directory: {root}")
    else:
        with doctor_operation_lock(root, errors):
            doctor_inspection(root, errors, warnings)
    for message in sorted(errors):
        print(f"skillset: error: {printable_text(message)}", file=sys.stderr)
    for message in sorted(warnings):
        print(f"skillset: warning: {printable_text(message)}", file=sys.stderr)
    return 1 if errors else 0
