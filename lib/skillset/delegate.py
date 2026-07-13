import os
import sys

from .errors import OperationalError
from .layout import validate_layout


SCOPED_SKILLS_COMMANDS = {"add", "list", "ls", "remove", "rm", "update"}
SCOPE_FREE_SKILLS_COMMANDS = {"find", "use", "init"}


def enforce_global_scope(upstream_arguments, command_parser):
    option_end = (
        upstream_arguments.index("--")
        if "--" in upstream_arguments
        else len(upstream_arguments)
    )
    scope_arguments = upstream_arguments[:option_end]
    if any(argument in ("-p", "--project") for argument in scope_arguments):
        command_parser.error(
            "project scope is not supported for managed skills; use global scope"
        )
    if not any(argument in ("-g", "--global") for argument in scope_arguments):
        upstream_arguments.insert(option_end, "--global")
    return upstream_arguments


def prepare_upstream_arguments(arguments, command_parser):
    upstream_arguments = list(arguments)
    if not upstream_arguments:
        return upstream_arguments
    command = upstream_arguments[0]
    if command in SCOPED_SKILLS_COMMANDS:
        return enforce_global_scope(upstream_arguments, command_parser)
    if command not in SCOPE_FREE_SKILLS_COMMANDS and not command.startswith("-"):
        print(
            "skillset: warning: unknown upstream command; global scope was not injected",
            file=sys.stderr,
            flush=True,
        )
    return upstream_arguments


def delegate_skills(root, arguments, home_lock, lock_file, command_parser):
    validate_layout(root)
    upstream_arguments = prepare_upstream_arguments(arguments, command_parser)

    child_environment = os.environ.copy()
    child_environment.pop("XDG_STATE_HOME", None)
    os.set_inheritable(home_lock, True)
    os.set_inheritable(lock_file.fileno(), True)
    try:
        os.execvpe(
            "npx", ["npx", "skills", *upstream_arguments], child_environment
        )
    except OSError as error:
        raise OperationalError(f"could not execute npx skills: {error}") from error
