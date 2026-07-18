"""Manage flattened skillset projections discovered by Claude Code."""

import os
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from errno import EINVAL
from pathlib import Path

from .errors import ClaudeInterrupted, OperationalError
from .layout import (
    NAME_PATTERN,
    lexists,
    real_kind,
    set_path,
    validate_layout,
    validate_name,
    validate_set,
)
from .metadata import list_named_sets, list_scoped_sets


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@dataclass(frozen=True)
class GlobalRegistrationBlocker:
    path: Path
    enabled: bool


def expected_target(root, name):
    return os.fspath((set_path(root, name) / "skills").absolute())


def scope_paths(root, scope):
    claude = (
        root.parent / ".claude" if scope == "global" else Path.cwd() / ".claude"
    )
    return claude, claude / "skills", claude / ".skillsets"


def scope_option(scope):
    return "" if scope == "global" else " --local"


def opposite_scope(scope):
    return "local" if scope == "global" else "global"


def validate_projection_root(source_path, scope):
    if scope != "local":
        return
    projection_root = Path.cwd() / ".claude"
    try:
        resolved_source = source_path.resolve(strict=True)
        resolved_projection = projection_root.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise OperationalError(
            "could not resolve Claude Code local projection containment: "
            f"{error}"
        ) from error
    if (
        resolved_source == resolved_projection
        or resolved_source in resolved_projection.parents
    ):
        raise OperationalError(
            "Claude Code local projection must not be rooted inside its "
            f"skill source: {projection_root} is inside {source_path}"
        )


def canonical_target(target, expected):
    return os.path.isabs(target) and target.rstrip("/") == expected


def canonical_link_at(directory_fd, name, target):
    try:
        metadata = os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False
        )
    except FileNotFoundError:
        return False
    except OSError as error:
        raise OperationalError(
            f"could not inspect Claude Code entry {name!r}: {error}"
        ) from error
    if not stat.S_ISLNK(metadata.st_mode):
        return False
    try:
        link_target = os.readlink(name, dir_fd=directory_fd)
    except FileNotFoundError:
        return False
    except OSError as error:
        if error.errno == EINVAL:
            return False
        raise OperationalError(
            f"could not inspect Claude Code entry {name!r}: {error}"
        ) from error
    return canonical_target(link_target, target)


def owned_link_at(directory_fd, name, registered_target):
    if Path(name).name != name:
        return False
    return canonical_link_at(
        directory_fd, name, os.path.join(registered_target, name)
    )


def _container_error(path):
    raise OperationalError(
        f"Claude Code container must be a real directory: {path}"
    )


def validate_scope_containers(root, scope):
    claude, skills, registrations = scope_paths(root, scope)
    if not lexists(claude):
        return claude, skills, registrations
    if not real_kind(claude, stat.S_ISDIR):
        _container_error(claude)
    for directory in (skills, registrations):
        if lexists(directory) and not real_kind(directory, stat.S_ISDIR):
            _container_error(directory)
    return claude, skills, registrations


@contextmanager
def open_directory(path):
    try:
        descriptor = os.open(path, DIRECTORY_FLAGS)
    except OSError as error:
        raise OperationalError(
            f"could not open real directory {path}: {error}"
        ) from error
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _identity(metadata):
    return metadata.st_dev, metadata.st_ino


def directory_binding_problem(path, descriptor):
    try:
        public_metadata = os.stat(path, follow_symlinks=False)
        opened_metadata = os.fstat(descriptor)
    except OSError as error:
        return f"directory changed during synchronization: {path}: {error}"
    if (
        not stat.S_ISDIR(public_metadata.st_mode)
        or _identity(public_metadata) != _identity(opened_metadata)
    ):
        return f"directory changed during synchronization: {path}"
    return None


def same_directory(first, second):
    try:
        first_metadata = os.stat(first, follow_symlinks=False)
        second_metadata = os.stat(second, follow_symlinks=False)
        return _identity(first_metadata) == _identity(second_metadata)
    except FileNotFoundError:
        try:
            return first.resolve(strict=False) == second.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise OperationalError(
                f"could not compare Claude Code scope roots: {error}"
            ) from error
    except OSError as error:
        raise OperationalError(
            f"could not compare Claude Code scope roots: {error}"
        ) from error


def ensure_scope_directories(root, scope, stack, expected_identities=None):
    expected_identities = {} if expected_identities is None else expected_identities
    claude, skills, registrations = validate_scope_containers(root, scope)
    if not lexists(claude):
        try:
            claude.mkdir()
        except FileExistsError:
            pass
        except OSError as error:
            raise OperationalError(
                f"could not create Claude Code container {claude}: {error}"
            ) from error
    claude_fd = stack.enter_context(open_directory(claude))
    if (
        "claude" in expected_identities
        and _identity(os.fstat(claude_fd)) != expected_identities["claude"]
    ):
        raise OperationalError(
            f"Claude Code container changed during inspection: {claude}"
        )
    for name, path in (("skills", skills), (".skillsets", registrations)):
        try:
            metadata = os.stat(
                name, dir_fd=claude_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            try:
                os.mkdir(name, dir_fd=claude_fd)
            except FileExistsError:
                pass
            except OSError as error:
                raise OperationalError(
                    f"could not create Claude Code container {path}: {error}"
                ) from error
        except OSError as error:
            raise OperationalError(
                f"could not inspect Claude Code container {path}: {error}"
            ) from error
        else:
            if not stat.S_ISDIR(metadata.st_mode):
                _container_error(path)
        try:
            descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=claude_fd)
        except OSError as error:
            raise OperationalError(
                f"could not open Claude Code container {path}: {error}"
            ) from error
        stack.callback(os.close, descriptor)
        if (
            name in expected_identities
            and _identity(os.fstat(descriptor)) != expected_identities[name]
        ):
            raise OperationalError(
                f"Claude Code container changed during inspection: {path}"
            )
        if name == "skills":
            skills_fd = descriptor
        else:
            registrations_fd = descriptor
    return skills, registrations, skills_fd, registrations_fd


def open_existing_scope(root, scope, stack):
    claude, skills, registrations = validate_scope_containers(root, scope)
    if not lexists(claude):
        return skills, registrations, None, None, {}
    claude_fd = stack.enter_context(open_directory(claude))
    identities = {"claude": _identity(os.fstat(claude_fd))}
    descriptors = []
    for name, path in (("skills", skills), (".skillsets", registrations)):
        try:
            descriptor = os.open(name, DIRECTORY_FLAGS, dir_fd=claude_fd)
        except FileNotFoundError:
            descriptor = None
        except OSError as error:
            raise OperationalError(
                f"could not open Claude Code container {path}: {error}"
            ) from error
        if descriptor is not None:
            stack.callback(os.close, descriptor)
            identities[name] = _identity(os.fstat(descriptor))
        descriptors.append(descriptor)
    return skills, registrations, *descriptors, identities


def source_inventory(source_fd, source_path):
    inventory = {}
    try:
        names = sorted(os.listdir(source_fd))
    except OSError as error:
        raise OperationalError(
            f"could not inspect Claude Code skill source {source_path}: {error}"
        ) from error
    for name in names:
        try:
            metadata = os.stat(
                name, dir_fd=source_fd, follow_symlinks=False
            )
        except OSError as error:
            raise OperationalError(
                f"could not inspect Claude Code skill source {source_path / name}: {error}"
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise OperationalError(
                f"Claude Code skill source must not be a symlink: {source_path / name}"
            )
        if stat.S_ISDIR(metadata.st_mode):
            inventory[name] = (metadata.st_dev, metadata.st_ino)
    return inventory


def open_source(root, name, stack):
    source_path = validate_set(root, name) / "skills"
    try:
        accepted = source_path.lstat()
    except OSError as error:
        raise OperationalError(
            f"could not inspect Claude Code skill source {source_path}: {error}"
        ) from error
    source_fd = stack.enter_context(open_directory(source_path))
    opened = os.fstat(source_fd)
    if (accepted.st_dev, accepted.st_ino) != (opened.st_dev, opened.st_ino):
        raise OperationalError(
            f"Claude Code skill source changed during inspection: {source_path}"
        )
    return source_path, source_fd, source_inventory(source_fd, source_path)


def _entry_missing(directory_fd, name):
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _recovery_message(root, name, scope, action, detail):
    _claude, skills, registrations = scope_paths(root, scope)
    source = set_path(root, name) / "skills"
    option = scope_option(scope)
    return (
        f"Claude Code {action} for {name!r} is incomplete ({detail}). "
        f"Registration: {registrations / name}; source: {source}; "
        f"projection: {skills}. Rerun `skillset claude {action} {name}{option}` "
        f"to recover"
    )


def _interrupted(root, name, scope, action, detail):
    raise ClaudeInterrupted(
        _recovery_message(root, name, scope, action, detail)
    )


def create_link(
    directory_fd, name, target, path, root, set_name, scope, action
):
    if canonical_link_at(directory_fd, name, target):
        return
    if not _entry_missing(directory_fd, name):
        raise OperationalError(f"Claude Code entry already exists: {path}")
    try:
        os.symlink(target, name, dir_fd=directory_fd)
    except KeyboardInterrupt:
        state = "link was created" if canonical_link_at(
            directory_fd, name, target
        ) else "link was not created"
        _interrupted(root, set_name, scope, action, f"{path}: {state}")
    except Exception as error:
        if canonical_link_at(directory_fd, name, target):
            return
        raise OperationalError(
            f"could not create Claude Code link {path}: {error}"
        ) from error


def unlink_link(
    directory_fd,
    name,
    path,
    predicate,
    root,
    set_name,
    scope,
    action,
):
    if not predicate():
        if _entry_missing(directory_fd, name):
            return
        raise OperationalError(
            f"refused to remove changed Claude Code entry: {path}"
        )
    try:
        os.unlink(name, dir_fd=directory_fd)
    except KeyboardInterrupt:
        state = "link was removed" if _entry_missing(
            directory_fd, name
        ) else "link remains"
        _interrupted(root, set_name, scope, action, f"{path}: {state}")
    except Exception as error:
        if _entry_missing(directory_fd, name):
            return
        raise OperationalError(
            f"could not remove Claude Code link {path}: {error}"
        ) from error


def preflight_projection(
    source_inventory_value,
    skills_fd,
    skills_path,
    registrations_fd,
    registration_path,
    target,
):
    if registrations_fd is not None and not _entry_missing(
        registrations_fd, registration_path.name
    ):
        if not canonical_link_at(
            registrations_fd, registration_path.name, target
        ):
            raise OperationalError(
                f"Claude Code skillset registration already exists: {registration_path}"
            )
    if skills_fd is None:
        return
    for skill_name in source_inventory_value:
        skill_target = os.path.join(target, skill_name)
        if canonical_link_at(skills_fd, skill_name, skill_target):
            continue
        if not _entry_missing(skills_fd, skill_name):
            raise OperationalError(
                f"Claude Code skill entry already exists: {skills_path / skill_name}"
            )


def cross_scope_collision(
    source_inventory_value,
    target,
    other_skills_fd,
    other_skills_path,
):
    if other_skills_fd is None:
        return None
    for skill_name in source_inventory_value:
        skill_target = os.path.join(target, skill_name)
        if canonical_link_at(other_skills_fd, skill_name, skill_target):
            continue
        if not _entry_missing(other_skills_fd, skill_name):
            return (
                f"Claude Code skill name {skill_name!r} conflicts across "
                "global and local scopes at "
                f"{other_skills_path / skill_name}"
            )
    return None


def verify_source_child(source_fd, source_path, name, identity):
    try:
        metadata = os.stat(
            name, dir_fd=source_fd, follow_symlinks=False
        )
    except OSError as error:
        raise OperationalError(
            f"Claude Code skill source changed during enable: {source_path / name}: {error}"
        ) from error
    if not stat.S_ISDIR(metadata.st_mode) or (
        metadata.st_dev,
        metadata.st_ino,
    ) != identity:
        raise OperationalError(
            f"Claude Code skill source changed during enable: {source_path / name}"
        )


def owned_names(skills_fd, registered_target):
    if skills_fd is None:
        return []
    try:
        names = os.listdir(skills_fd)
    except OSError as error:
        raise OperationalError(
            f"could not inspect Claude Code projection for {registered_target}: {error}"
        ) from error
    return sorted(
        name
        for name in names
        if owned_link_at(skills_fd, name, registered_target)
    )


def verify_enabled(
    source_fd,
    source_path,
    skills_fd,
    skills_path,
    registrations_fd,
    registration_path,
    target,
):
    current = source_inventory(source_fd, source_path)
    if registrations_fd is None or not canonical_link_at(
        registrations_fd, registration_path.name, target
    ):
        return f"registration is missing or noncanonical: {registration_path}"
    if skills_fd is None:
        return f"projection directory is missing: {skills_path}"
    for skill_name in current:
        if not canonical_link_at(
            skills_fd, skill_name, os.path.join(target, skill_name)
        ):
            return f"projected skill is missing or colliding: {skills_path / skill_name}"
    stale = set(owned_names(skills_fd, target)) - set(current)
    if stale:
        return f"stale projected skill remains: {skills_path / sorted(stale)[0]}"
    for path, descriptor in (
        (source_path, source_fd),
        (skills_path, skills_fd),
        (registration_path.parent, registrations_fd),
    ):
        problem = directory_binding_problem(path, descriptor)
        if problem is not None:
            return problem
    return None


def enable(root, name, scope):
    validate_name(name)
    validate_layout(root)
    target = expected_target(root, name)
    registration_created = False
    with ExitStack() as stack:
        source_path, source_fd, inventory = open_source(root, name, stack)
        validate_projection_root(source_path, scope)
        other_skills_path = None
        other_skills_fd = None
        if not same_directory(
            scope_paths(root, "global")[0],
            scope_paths(root, "local")[0],
        ):
            (
                other_skills_path,
                _other_registrations_path,
                other_skills_fd,
                _other_registrations_fd,
                _other_scope_identities,
            ) = open_existing_scope(root, opposite_scope(scope), stack)
            problem = cross_scope_collision(
                inventory,
                target,
                other_skills_fd,
                other_skills_path,
            )
            if problem is not None:
                raise OperationalError(problem)
        (
            skills_path,
            registrations_path,
            old_skills_fd,
            old_registrations_fd,
            scope_identities,
        ) = open_existing_scope(root, scope, stack)
        registration_path = registrations_path / name
        preflight_projection(
            inventory,
            old_skills_fd,
            skills_path,
            old_registrations_fd,
            registration_path,
            target,
        )
        was_registered = (
            old_registrations_fd is not None
            and canonical_link_at(old_registrations_fd, name, target)
        )
        skills_fd = None
        registrations_fd = None
        try:
            (
                skills_path,
                registrations_path,
                skills_fd,
                registrations_fd,
            ) = ensure_scope_directories(
                root, scope, stack, expected_identities=scope_identities
            )
            registration_path = registrations_path / name
            create_link(
                registrations_fd,
                name,
                target,
                registration_path,
                root,
                name,
                scope,
                "enable",
            )
            registration_created = not was_registered
            for skill_name, identity in inventory.items():
                verify_source_child(
                    source_fd, source_path, skill_name, identity
                )
                create_link(
                    skills_fd,
                    skill_name,
                    os.path.join(target, skill_name),
                    skills_path / skill_name,
                    root,
                    name,
                    scope,
                    "enable",
                )
            for stale_name in (
                set(owned_names(skills_fd, target)) - set(inventory)
            ):
                stale_path = skills_path / stale_name
                unlink_link(
                    skills_fd,
                    stale_name,
                    stale_path,
                    lambda stale_name=stale_name: owned_link_at(
                        skills_fd, stale_name, target
                    ),
                    root,
                    name,
                    scope,
                    "enable",
                )
            problem = verify_enabled(
                source_fd,
                source_path,
                skills_fd,
                skills_path,
                registrations_fd,
                registration_path,
                target,
            )
            if problem is not None:
                raise OperationalError(problem)
            if other_skills_path is not None:
                if other_skills_fd is None:
                    (
                        other_skills_path,
                        _other_registrations_path,
                        other_skills_fd,
                        _other_registrations_fd,
                        _other_scope_identities,
                    ) = open_existing_scope(
                        root, opposite_scope(scope), stack
                    )
                problem = cross_scope_collision(
                    inventory,
                    target,
                    other_skills_fd,
                    other_skills_path,
                )
                if problem is not None:
                    raise OperationalError(problem)
                if other_skills_fd is not None:
                    problem = directory_binding_problem(
                        other_skills_path, other_skills_fd
                    )
                    if problem is not None:
                        raise OperationalError(problem)
        except ClaudeInterrupted:
            raise
        except KeyboardInterrupt:
            if (
                was_registered
                or registration_created
                or (
                    registrations_fd is not None
                    and canonical_link_at(registrations_fd, name, target)
                )
            ):
                _interrupted(
                    root,
                    name,
                    scope,
                    "enable",
                    "registration exists and projection may be incomplete",
                )
            raise
        except OperationalError as error:
            if (
                was_registered
                or registration_created
                or (
                    registrations_fd is not None
                    and canonical_link_at(registrations_fd, name, target)
                )
            ):
                raise OperationalError(
                    _recovery_message(root, name, scope, "enable", error)
                ) from error
            raise


def disable(root, name, scope):
    validate_name(name)
    validate_layout(root)
    target = expected_target(root, name)
    with ExitStack() as stack:
        (
            skills_path,
            registrations_path,
            skills_fd,
            registrations_fd,
            _scope_identities,
        ) = open_existing_scope(root, scope, stack)
        registration_path = registrations_path / name
        registration_missing = (
            registrations_fd is None
            or _entry_missing(registrations_fd, name)
        )
        if not registration_missing and not canonical_link_at(
            registrations_fd, name, target
        ):
            raise OperationalError(
                f"skillset is not Claude Code-enabled: {name!r}"
            )
        try:
            for skill_name in owned_names(skills_fd, target):
                skill_path = skills_path / skill_name
                unlink_link(
                    skills_fd,
                    skill_name,
                    skill_path,
                    lambda skill_name=skill_name: owned_link_at(
                        skills_fd, skill_name, target
                    ),
                    root,
                    name,
                    scope,
                    "disable",
                )
            if registrations_fd is not None:
                unlink_link(
                    registrations_fd,
                    name,
                    registration_path,
                    lambda: canonical_link_at(
                        registrations_fd, name, target
                    ),
                    root,
                    name,
                    scope,
                    "disable",
                )
            remaining = owned_names(skills_fd, target)
            registration_remains = (
                registrations_fd is not None
                and not _entry_missing(registrations_fd, name)
            )
            if remaining or registration_remains:
                path = (
                    skills_path / remaining[0]
                    if remaining
                    else registration_path
                )
                raise OperationalError(f"managed entry remains: {path}")
        except ClaudeInterrupted:
            raise
        except KeyboardInterrupt:
            _interrupted(
                root,
                name,
                scope,
                "disable",
                "registration and projection may be incomplete",
            )
        except OperationalError as error:
            raise OperationalError(
                _recovery_message(root, name, scope, "disable", error)
            ) from error


def synchronized_names(root, scope):
    with ExitStack() as stack:
        (
            skills_path,
            registrations_path,
            skills_fd,
            registrations_fd,
            _scope_identities,
        ) = open_existing_scope(root, scope, stack)
        if registrations_fd is None:
            return []
        names = []
        label = "global" if scope == "global" else "local"
        try:
            registration_names = sorted(os.listdir(registrations_fd))
        except OSError as error:
            raise OperationalError(
                f"could not inspect Claude Code registrations in {label} "
                f"scope at {registrations_path}: {error}"
            ) from error
        for name in registration_names:
            if not NAME_PATTERN.fullmatch(name):
                continue
            target = expected_target(root, name)
            registration_path = registrations_path / name
            if not canonical_link_at(registrations_fd, name, target):
                raise OperationalError(
                    f"noncanonical Claude Code registration in {label} scope: "
                    f"{registration_path}; repair it manually or run "
                    f"`skillset claude disable {name}{scope_option(scope)}` "
                    "after restoring the canonical link"
                )
            with ExitStack() as source_stack:
                try:
                    source_path, source_fd, _inventory = open_source(
                        root, name, source_stack
                    )
                except OperationalError as error:
                    raise OperationalError(
                        f"invalid Claude Code registration in {label} scope: "
                        f"{registration_path}: {error}; restore the source or "
                        f"run `skillset claude disable {name}{scope_option(scope)}`"
                    ) from error
                problem = verify_enabled(
                    source_fd,
                    source_path,
                    skills_fd,
                    skills_path,
                    registrations_fd,
                    registration_path,
                    target,
                )
            if problem is not None:
                raise OperationalError(
                    f"incomplete Claude Code projection in {label} scope for "
                    f"{name!r}: {problem}; rerun "
                    f"`skillset claude enable {name}{scope_option(scope)}` "
                    f"or `skillset claude disable {name}{scope_option(scope)}`"
                )
            names.append(name)
        return names


def validate_names_against_other_scope(root, scope, names):
    if not names:
        return
    if same_directory(
        scope_paths(root, "global")[0],
        scope_paths(root, "local")[0],
    ):
        return
    other_scope_name = opposite_scope(scope)
    with ExitStack() as stack:
        (
            other_skills_path,
            _other_registrations_path,
            other_skills_fd,
            _other_registrations_fd,
            _other_scope_identities,
        ) = open_existing_scope(root, other_scope_name, stack)
        if other_skills_fd is None:
            return
        for name in names:
            with ExitStack() as source_stack:
                source_path, source_fd, inventory = open_source(
                    root, name, source_stack
                )
                problem = cross_scope_collision(
                    inventory,
                    expected_target(root, name),
                    other_skills_fd,
                    other_skills_path,
                )
                if problem is not None:
                    raise OperationalError(problem)
                problem = directory_binding_problem(source_path, source_fd)
                if problem is not None:
                    raise OperationalError(problem)
        problem = directory_binding_problem(
            other_skills_path, other_skills_fd
        )
        if problem is not None:
            raise OperationalError(problem)


def list_enabled(root, verbose, scope):
    validate_layout(root)
    if scope == "all":
        global_root = scope_paths(root, "global")[0]
        local_root = scope_paths(root, "local")[0]
        global_names = synchronized_names(root, "global")
        local_names = (
            []
            if same_directory(global_root, local_root)
            else synchronized_names(root, "local")
        )
        validate_names_against_other_scope(root, "global", global_names)
        validate_names_against_other_scope(root, "local", local_names)
        return list_scoped_sets(
            root,
            (
                ("g", global_names),
                ("l", local_names),
            ),
            verbose,
        )
    names = synchronized_names(root, scope)
    validate_names_against_other_scope(root, scope, names)
    return list_named_sets(
        root,
        names,
        verbose,
        mark_active=False,
    )


def global_registration_blocker(root, name):
    claude, _skills, registrations = scope_paths(root, "global")
    try:
        claude_metadata = claude.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return GlobalRegistrationBlocker(claude, False)
    if stat.S_ISLNK(claude_metadata.st_mode) or not stat.S_ISDIR(
        claude_metadata.st_mode
    ):
        return GlobalRegistrationBlocker(claude, False)
    try:
        registrations_metadata = registrations.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return GlobalRegistrationBlocker(claude, False)
    if stat.S_ISLNK(registrations_metadata.st_mode) or not stat.S_ISDIR(
        registrations_metadata.st_mode
    ):
        return GlobalRegistrationBlocker(registrations, False)
    registration = registrations / name
    try:
        registration_metadata = registration.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return GlobalRegistrationBlocker(registrations, False)
    if not stat.S_ISLNK(registration_metadata.st_mode):
        return GlobalRegistrationBlocker(registration, False)
    try:
        target = os.readlink(registration)
    except FileNotFoundError:
        return None
    except OSError:
        return GlobalRegistrationBlocker(registration, False)
    return GlobalRegistrationBlocker(
        registration,
        canonical_target(target, expected_target(root, name)),
    )
