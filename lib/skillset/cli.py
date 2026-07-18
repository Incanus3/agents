"""Parse and dispatch skillset CLI commands."""

import argparse
import sys
from pathlib import Path

from .claude import disable as claude_disable
from .claude import enable as claude_enable
from .claude import list_enabled as list_claude_enabled
from .completions import emit_completions
from .codex import disable as codex_disable
from .codex import enable as codex_enable
from .codex import list_enabled as list_codex_enabled
from .delegate import delegate_skills
from .doctor import doctor
from .errors import ClaudeInterrupted, OperationalError
from .layout import operation_lock, stable_home_lock
from .metadata import current, list_sets, printable_text, show
from .operations import create, init, remove, rename, use


class SkillsetArgumentParser(argparse.ArgumentParser):
    """Let domain validation handle option-like skillset names."""

    def _parse_optional(self, argument):
        parsed = super()._parse_optional(argument)
        if parsed is not None:
            candidates = parsed if isinstance(parsed, list) else [parsed]
            if candidates and all(candidate[0] is None for candidate in candidates):
                return None
        return parsed


def parser():
    command_parser = SkillsetArgumentParser(prog="skillset")
    commands = command_parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="adopt existing global skills")
    init_parser.add_argument("name")
    create_parser = commands.add_parser("create", help="create a skillset")
    create_parser.add_argument("name")
    source_group = create_parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "-f",
        "--from",
        dest="source",
        metavar="SOURCE",
        help="clone from an existing skillset",
    )
    source_group.add_argument(
        "--manual",
        action="store_true",
        help="create a hand-managed skillset without upstream lock metadata",
    )
    create_parser.add_argument(
        "--use",
        dest="activate",
        action="store_true",
        help="activate the created skillset",
    )
    use_parser = commands.add_parser("use", help="activate a skillset")
    use_parser.add_argument("name")
    rename_parser = commands.add_parser("rename", help="rename a skillset")
    rename_parser.add_argument("old")
    rename_parser.add_argument("new")
    remove_parser = commands.add_parser("remove", help="remove an inactive skillset")
    remove_parser.add_argument("name")
    remove_parser.add_argument("--yes", action="store_true")
    list_parser = commands.add_parser("list", help="list managed skillsets")
    list_parser.add_argument("-v", "--verbose", action="store_true")
    codex_parser = commands.add_parser(
        "codex", help="manage Codex-enabled skillsets"
    )
    codex_commands = codex_parser.add_subparsers(
        dest="codex_command", required=True
    )
    codex_enable_parser = codex_commands.add_parser(
        "enable", help="enable a skillset for Codex"
    )
    codex_enable_parser.add_argument("name")
    add_codex_scope_options(codex_enable_parser)
    codex_disable_parser = codex_commands.add_parser(
        "disable", help="disable a skillset for Codex"
    )
    codex_disable_parser.add_argument("name")
    add_codex_scope_options(codex_disable_parser)
    codex_list_parser = codex_commands.add_parser(
        "list", help="list Codex-enabled skillsets"
    )
    codex_list_parser.add_argument("-v", "--verbose", action="store_true")
    add_codex_scope_options(codex_list_parser, default="all")
    claude_parser = commands.add_parser(
        "claude", help="manage Claude Code-enabled skillsets"
    )
    claude_commands = claude_parser.add_subparsers(
        dest="claude_command", required=True
    )
    claude_enable_parser = claude_commands.add_parser(
        "enable", help="enable a skillset for Claude Code"
    )
    claude_enable_parser.add_argument("name")
    add_claude_scope_options(claude_enable_parser)
    claude_disable_parser = claude_commands.add_parser(
        "disable", help="disable a skillset for Claude Code"
    )
    claude_disable_parser.add_argument("name")
    add_claude_scope_options(claude_disable_parser)
    claude_list_parser = claude_commands.add_parser(
        "list", help="list Claude Code-enabled skillsets"
    )
    claude_list_parser.add_argument("-v", "--verbose", action="store_true")
    add_claude_scope_options(claude_list_parser, default="all")
    commands.add_parser("current", help="print the active skillset name")
    show_parser = commands.add_parser("show", help="show skills in a skillset")
    show_parser.add_argument("name", nargs="?")
    doctor_parser = commands.add_parser("doctor", help="diagnose the managed layout")
    doctor_parser.add_argument(
        "--fix",
        action="store_true",
        help="create safe missing replacement files after confirmation",
    )
    completions_parser = commands.add_parser(
        "completions", help="emit a shell completion script"
    )
    completions_parser.add_argument("shell", choices=("bash", "zsh", "fish"))
    skills_parser = commands.add_parser(
        "skills", help="run managed upstream skills", add_help=False
    )
    skills_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return command_parser


def add_codex_scope_options(command_parser, default="global"):
    scope = command_parser.add_mutually_exclusive_group()
    scope.add_argument(
        "-g",
        "--global",
        dest="codex_scope",
        action="store_const",
        const="global",
        help="manage the global ~/.codex directory (default)",
    )
    scope.add_argument(
        "-l",
        "--local",
        dest="codex_scope",
        action="store_const",
        const="local",
        help="manage the current directory's .codex directory",
    )
    command_parser.set_defaults(codex_scope=default)


def add_claude_scope_options(command_parser, default="global"):
    scope = command_parser.add_mutually_exclusive_group()
    scope.add_argument(
        "-g",
        "--global",
        dest="claude_scope",
        action="store_const",
        const="global",
        help="manage the global ~/.claude directory (default)",
    )
    scope.add_argument(
        "-l",
        "--local",
        dest="claude_scope",
        action="store_const",
        const="local",
        help="manage the current directory's .claude directory",
    )
    command_parser.set_defaults(claude_scope=default)


def dispatch_locked_command(root, arguments, home_lock, lock_file, command_parser):
    if arguments.command == "init":
        init(root, arguments.name)
    elif arguments.command == "create":
        create(root, arguments.name, arguments.source, arguments.manual)
        if arguments.activate:
            use(root, arguments.name)
    elif arguments.command == "use":
        use(root, arguments.name)
    elif arguments.command == "rename":
        rename(root, arguments.old, arguments.new)
    elif arguments.command == "remove":
        remove(root, arguments.name, arguments.yes)
    elif arguments.command == "list":
        list_sets(root, arguments.verbose)
    elif arguments.command == "codex":
        if arguments.codex_command == "enable":
            codex_enable(root, arguments.name, arguments.codex_scope)
        elif arguments.codex_command == "disable":
            codex_disable(root, arguments.name, arguments.codex_scope)
        elif arguments.codex_command == "list":
            list_codex_enabled(root, arguments.verbose, arguments.codex_scope)
        else:
            raise OperationalError(
                f"unsupported Codex command: {arguments.codex_command}"
            )
    elif arguments.command == "claude":
        if arguments.claude_command == "enable":
            claude_enable(root, arguments.name, arguments.claude_scope)
        elif arguments.claude_command == "disable":
            claude_disable(root, arguments.name, arguments.claude_scope)
        elif arguments.claude_command == "list":
            list_claude_enabled(
                root, arguments.verbose, arguments.claude_scope
            )
        else:
            raise OperationalError(
                f"unsupported Claude Code command: {arguments.claude_command}"
            )
    elif arguments.command == "current":
        current(root)
    elif arguments.command == "show":
        show(root, arguments.name)
    elif arguments.command == "skills":
        delegate_skills(
            root,
            arguments.arguments,
            home_lock,
            lock_file,
            command_parser,
        )
    else:
        raise OperationalError(f"unsupported command: {arguments.command}")


def run_managed_command(root, arguments, command_parser):
    inspection = arguments.command in {"list", "current", "show"} or (
        arguments.command == "codex" and arguments.codex_command == "list"
    ) or (
        arguments.command == "claude" and arguments.claude_command == "list"
    )
    with stable_home_lock(root) as home_lock:
        if arguments.command == "doctor":
            return doctor(root, fix=arguments.fix)
        with operation_lock(root, create=not inspection) as lock_file:
            dispatch_locked_command(
                root, arguments, home_lock, lock_file, command_parser
            )
    return 0


def format_command_error(command, error, unexpected=False):
    if command == "doctor":
        message = f"doctor inspection failed: {error}" if unexpected else error
        return f"skillset: error: {printable_text(message)}"
    prefix = "operation failed: " if unexpected else ""
    return f"skillset: {prefix}{printable_text(error)}"


def main():
    command_parser = parser()
    arguments = command_parser.parse_args()
    if arguments.command == "completions":
        emit_completions(arguments.shell)
        return 0
    root = Path.home() / ".agents"
    try:
        return run_managed_command(root, arguments, command_parser)
    except ClaudeInterrupted as error:
        print(
            f"skillset: interrupted: {printable_text(error.message)}",
            file=sys.stderr,
        )
        return 130
    except OperationalError as error:
        print(format_command_error(arguments.command, error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("skillset: interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        print(
            format_command_error(arguments.command, error, unexpected=True),
            file=sys.stderr,
        )
        return 1
