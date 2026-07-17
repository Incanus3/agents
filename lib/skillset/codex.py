"""Manage named skillset links discovered by Codex."""

import os
import stat
from pathlib import Path

from .errors import OperationalError
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


def expected_target(root, name):
    validate_name(name)
    return os.fspath((root / "skillsets" / name / "skills").absolute())


def codex_skills_directory(root, scope, create):
    codex = (
        root.parent / ".codex" if scope == "global" else Path.cwd() / ".codex"
    )
    skills = codex / "skills"
    for directory in (codex, skills):
        if lexists(directory):
            if not real_kind(directory, stat.S_ISDIR):
                raise OperationalError(
                    f"Codex skills container must be a real directory: {directory}"
                )
            continue
        if not create:
            return None
        try:
            directory.mkdir()
        except OSError as error:
            raise OperationalError(
                f"could not create Codex skills container {directory}: {error}"
            ) from error
    return skills


def canonical_link(root, name, scope="global"):
    skills = codex_skills_directory(root, scope, create=False)
    if skills is None:
        return False
    link = skills / name
    try:
        target = os.readlink(link)
        return (
            link.is_symlink()
            and os.path.isabs(target)
            and os.path.normpath(target) == expected_target(root, name)
        )
    except OSError:
        return False


def enable(root, name, scope):
    validate_name(name)
    validate_layout(root)
    validate_set(root, name)
    skills = codex_skills_directory(root, scope, create=True)
    link = skills / name
    target = expected_target(root, name)
    if lexists(link):
        if canonical_link(root, name, scope):
            return
        raise OperationalError(f"Codex skillset entry already exists: {link}")
    try:
        os.symlink(target, link)
    except OSError as error:
        raise OperationalError(
            f"could not enable Codex skillset {name!r}: {error}"
        ) from error


def disable(root, name, scope):
    validate_name(name)
    validate_layout(root)
    skills = codex_skills_directory(root, scope, create=False)
    link = None if skills is None else skills / name
    if link is None or not canonical_link(root, name, scope):
        raise OperationalError(f"skillset is not Codex-enabled: {name!r}")
    try:
        link.unlink()
    except OSError as error:
        raise OperationalError(
            f"could not disable Codex skillset {name!r}: {error}"
        ) from error


def enabled_names(root, scope):
    skills = codex_skills_directory(root, scope, create=False)
    if skills is None:
        return []
    names = []
    for entry in skills.iterdir():
        if not NAME_PATTERN.fullmatch(entry.name) or not canonical_link(
            root, entry.name, scope
        ):
            continue
        try:
            validate_set(root, entry.name)
        except OperationalError:
            continue
        names.append(entry.name)
    return sorted(names)


def list_enabled(root, verbose, scope):
    validate_layout(root)
    if scope == "all":
        global_skills = codex_skills_directory(root, "global", create=False)
        local_skills = codex_skills_directory(root, "local", create=False)
        local_names = (
            []
            if global_skills is not None and global_skills == local_skills
            else enabled_names(root, "local")
        )
        return list_scoped_sets(
            root,
            (("g", enabled_names(root, "global")), ("l", local_names)),
            verbose,
        )
    return list_named_sets(
        root,
        enabled_names(root, scope),
        verbose,
        mark_active=False,
    )
