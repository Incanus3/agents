"""Parse and dispatch skillset CLI commands."""

import argparse
import sys
from pathlib import Path

from .completions import emit_completions
from .delegate import delegate_skills
from .doctor import doctor
from .errors import OperationalError
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
    create_parser.add_argument(
        "-f",
        "--from",
        dest="source",
        metavar="SOURCE",
        help="clone from an existing skillset",
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
    commands.add_parser("current", help="print the active skillset name")
    show_parser = commands.add_parser("show", help="show skills in a skillset")
    show_parser.add_argument("name", nargs="?")
    commands.add_parser("doctor", help="diagnose the managed layout")
    completions_parser = commands.add_parser(
        "completions", help="emit a shell completion script"
    )
    completions_parser.add_argument("shell", choices=("bash", "zsh", "fish"))
    skills_parser = commands.add_parser(
        "skills", help="run managed upstream skills", add_help=False
    )
    skills_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return command_parser


def main():
    command_parser = parser()
    arguments = command_parser.parse_args()
    if arguments.command == "completions":
        emit_completions(arguments.shell)
        return 0
    root = Path.home() / ".agents"
    inspection = arguments.command in {"list", "current", "show"}
    status = 0
    try:
        with stable_home_lock(root) as home_lock:
            if arguments.command == "doctor":
                status = doctor(root)
            else:
                with operation_lock(root, create=not inspection) as lock_file:
                    if arguments.command == "init":
                        init(root, arguments.name)
                    elif arguments.command == "create":
                        create(root, arguments.name, arguments.source)
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
                        raise OperationalError(
                            f"unsupported command: {arguments.command}"
                        )
    except OperationalError as error:
        if arguments.command == "doctor":
            print(f"skillset: error: {printable_text(error)}", file=sys.stderr)
        else:
            print(f"skillset: {printable_text(error)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("skillset: interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        if arguments.command == "doctor":
            finding = f"doctor inspection failed: {error}"
            print(
                f"skillset: error: {printable_text(finding)}",
                file=sys.stderr,
            )
        else:
            print(
                f"skillset: operation failed: {printable_text(error)}",
                file=sys.stderr,
            )
        return 1
    return status
