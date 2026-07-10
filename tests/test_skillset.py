import fcntl
import json
import os
import re
import signal
import shutil
import stat
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILLSET = REPOSITORY_ROOT / "bin" / "skillset"
EMPTY_LOCK = {"version": 3, "skills": {}, "dismissed": {}}


class SkillsetTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.sandbox = Path(self.temporary_directory.name)
        self.home = self.new_home("home")
        self.root = self.home / ".agents"

    def new_home(self, name):
        home = self.sandbox / name
        home.mkdir()
        return home

    def environment(self, home=None, extra=None):
        environment = os.environ.copy()
        environment["HOME"] = str(home or self.home)
        environment["USERPROFILE"] = str(home or self.home)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment.pop("XDG_STATE_HOME", None)
        environment.pop("PYTHONHOME", None)
        environment.pop("PYTHONPATH", None)
        if extra:
            environment.update(extra)
        return environment

    def run_cli(
        self,
        *arguments,
        home=None,
        extra_environment=None,
        input_text=None,
        timeout=5,
    ):
        return subprocess.run(
            [str(SKILLSET), *arguments],
            cwd=home or self.home,
            env=self.environment(home, extra_environment),
            text=True,
            input=input_text,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def popen_cli(
        self,
        *arguments,
        home=None,
        extra_environment=None,
        start_new_session=False,
    ):
        return subprocess.Popen(
            [str(SKILLSET), *arguments],
            cwd=home or self.home,
            env=self.environment(home, extra_environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=start_new_session,
        )

    def write_lock(self, path, value=EMPTY_LOCK, *, raw=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = raw if raw is not None else json.dumps(value) + "\n"
        path.write_text(data, encoding="utf-8")

    def make_set(self, root, name, lock=EMPTY_LOCK):
        skillset = root / "skillsets" / name
        (skillset / "skills").mkdir(parents=True)
        self.write_lock(skillset / ".skill-lock.json", lock)
        return skillset

    def make_managed_layout(self, home, name="default"):
        root = home / ".agents"
        self.make_set(root, name)
        (root / "active").symlink_to(f"skillsets/{name}")
        (root / "skills").symlink_to("active/skills")
        (root / ".skill-lock.json").symlink_to("active/.skill-lock.json")
        return root

    def initialize(self, name="default", home=None):
        result = self.run_cli("init", name, home=home)
        self.assertEqual(result.returncode, 0, result.stderr)
        return (home or self.home) / ".agents"

    def assert_aliases(self, root, active):
        expected = {
            "active": f"skillsets/{active}",
            "skills": "active/skills",
            ".skill-lock.json": "active/.skill-lock.json",
        }
        for name, target in expected.items():
            path = root / name
            self.assertTrue(path.is_symlink(), path)
            self.assertEqual(os.readlink(path), target)

    def assert_empty_set(self, root, name):
        skillset = root / "skillsets" / name
        self.assertTrue(skillset.is_dir())
        self.assertFalse(skillset.is_symlink())
        self.assertEqual(list((skillset / "skills").iterdir()), [])
        self.assertEqual(
            json.loads((skillset / ".skill-lock.json").read_text(encoding="utf-8")),
            EMPTY_LOCK,
        )

    def write_skill(self, skills, directory, metadata, body=""):
        skill = skills / directory
        skill.mkdir()
        frontmatter = textwrap.dedent(metadata).strip("\n")
        skill.joinpath("SKILL.md").write_text(
            f"---\n{frontmatter}\n---\n{body}", encoding="utf-8"
        )
        return skill

    def filesystem_snapshot(self, root):
        snapshot = {}

        def visit(path, relative):
            metadata = path.lstat()
            kind = stat.S_IFMT(metadata.st_mode)
            payload = None
            if stat.S_ISLNK(metadata.st_mode):
                payload = os.readlink(path)
            elif stat.S_ISREG(metadata.st_mode):
                payload = path.read_bytes()
            snapshot[str(relative)] = (
                kind,
                stat.S_IMODE(metadata.st_mode),
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
                payload,
            )
            if stat.S_ISDIR(metadata.st_mode):
                with os.scandir(path) as entries:
                    for entry in sorted(entries, key=lambda item: item.name):
                        visit(Path(entry.path), relative / entry.name)

        visit(root, Path("."))
        return snapshot

    def assert_invalid_show_entry(self, output, directory, category):
        prefix = f"{directory} — [invalid: "
        matches = [line for line in output.splitlines() if line.startswith(prefix)]
        self.assertEqual(len(matches), 1, (directory, output))
        self.assertIn(category.lower(), matches[0].lower())

    def fault_environment(self, source):
        directory = self.sandbox / f"fault-{len(list(self.sandbox.glob('fault-*')))}"
        directory.mkdir()
        (directory / "sitecustomize.py").write_text(
            textwrap.dedent(source), encoding="utf-8"
        )
        return {"PYTHONPATH": str(directory)}

    def fake_npx_environment(self, home=None):
        home = home or self.home
        directory = home / "fake-bin"
        directory.mkdir(exist_ok=True)
        executable = directory / "npx"
        executable.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import os
                import signal
                import sys
                import time
                from pathlib import Path

                def write_marker(variable, value=""):
                    path = os.environ.get(variable)
                    if path:
                        Path(path).write_text(str(value), encoding="utf-8")

                record = os.environ.get("FAKE_NPX_RECORD")
                if record:
                    Path(record).write_text(json.dumps({
                        "argv": sys.argv[1:],
                        "environment": {
                            "XDG_STATE_HOME_present": "XDG_STATE_HOME" in os.environ,
                            "XDG_STATE_HOME": os.environ.get("XDG_STATE_HOME"),
                        },
                        "pid": os.getpid(),
                    }), encoding="utf-8")

                def handle_signal(number, _frame):
                    write_marker("FAKE_NPX_SIGNAL", number)
                    raise SystemExit(int(os.environ.get("FAKE_NPX_SIGNAL_STATUS", "128")))

                signal.signal(signal.SIGINT, handle_signal)
                signal.signal(signal.SIGTERM, handle_signal)
                write_marker("FAKE_NPX_READY", os.getpid())
                if os.environ.get("FAKE_NPX_ECHO_STDIN"):
                    data = sys.stdin.read()
                    sys.stdout.write(data)
                    sys.stdout.flush()
                    sys.stderr.write(data)
                    sys.stderr.flush()
                wait_path = os.environ.get("FAKE_NPX_WAIT_FOR")
                while wait_path and not Path(wait_path).exists():
                    time.sleep(0.01)
                raise SystemExit(int(os.environ.get("FAKE_NPX_STATUS", "0")))
                """
            ),
            encoding="utf-8",
        )
        executable.chmod(0o755)
        record = home / "fake-npx-record.json"
        return {
            "PATH": str(directory) + os.pathsep + os.environ.get("PATH", ""),
            "FAKE_NPX_RECORD": str(record),
        }, record

    def wait_for_path(self, path, process=None, timeout=5):
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                self.fail(f"process exited before creating {path}: {process.communicate()}")
            time.sleep(0.01)
        self.assertTrue(path.exists(), f"timed out waiting for {path}")

    def wait_for_pid_exit(self, pid, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
        self.fail(f"delegated child {pid} remained alive")

    def assert_fake_argv(self, record, expected):
        self.assertTrue(record.exists(), "fake npx was not invoked")
        payload = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(payload["argv"], expected)
        return payload

    def assert_refused(self, result):
        self.assertEqual(result.returncode, 1, (result.stdout, result.stderr))

    def test_help_includes_exact_commands_through_bead_three(self):
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        command_group = re.search(r"\{([^}]+)\}", result.stdout)
        self.assertIsNotNone(command_group, result.stdout)
        self.assertEqual(
            set(command_group.group(1).split(",")),
            {"init", "create", "use", "skills", "list", "current", "show"},
        )

    def test_list_sorts_set_names_and_marks_only_the_active_set(self):
        self.initialize("middle")
        self.make_set(self.root, "zeta")
        self.make_set(self.root, "alpha")

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "alpha\n* middle\nzeta\n")
        self.assertEqual(result.stderr, "")

    def test_list_supports_both_verbose_flags_with_sorted_valid_declared_names(self):
        self.initialize()
        empty = self.make_set(self.root, "empty")
        skills = self.root / "skillsets" / "default" / "skills"
        self.write_skill(skills, "second-directory", """
            name: zeta
            description: Last declared skill
        """)
        self.write_skill(skills, "first-directory", """
            name: alpha
            description: First declared skill
        """)
        self.write_skill(skills, "malformed", """
            name: hidden
        """)
        (skills / "ordinary-file.txt").write_text("ignored\n", encoding="utf-8")
        self.assertEqual(list((empty / "skills").iterdir()), [])

        expected = "* default\talpha, zeta\nempty\t(no skills)\n"
        for flag in ("-v", "--verbose"):
            with self.subTest(flag=flag):
                result = self.run_cli("list", flag)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.stderr, "")

    def test_current_prints_exact_active_name_before_and_after_use(self):
        self.initialize("default")
        self.make_set(self.root, "experiment")

        before = self.run_cli("current")
        switched = self.run_cli("use", "experiment")
        after = self.run_cli("current")

        self.assertEqual(before.returncode, 0, before.stderr)
        self.assertEqual(before.stdout, "default\n")
        self.assertEqual(before.stderr, "")
        self.assertEqual(switched.returncode, 0, switched.stderr)
        self.assertEqual(after.returncode, 0, after.stderr)
        self.assertEqual(after.stdout, "experiment\n")
        self.assertEqual(after.stderr, "")

    def test_show_empty_set_has_empty_output(self):
        self.initialize()

        result = self.run_cli("show", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_show_parses_supported_frontmatter_scalars_and_normalizes_descriptions(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        self.write_skill(skills, "plain-directory", """
            name: alpha
            description: plain description
            extra-key: [ignored, collection]
        """, body="Body content is ignored, even with name: misleading.\n")
        self.write_skill(skills, "single-directory", """
            name: 'o''brien'
            description: 'single ''quoted'' description'
        """)
        self.write_skill(skills, "double-directory", r'''
            name: "double"
            description: "first\nsecond\t\"quoted\" and \\ slash"
        ''')
        self.write_skill(skills, "literal-directory", """
            name: |
              literal
            description: |
              first line
              second   line
        """)
        self.write_skill(skills, "folded-directory", """
            name: >
              folded
            description: >
              folded line
              next   line
        """)
        self.write_skill(skills, "multiline-plain-directory", """
            name: multi-plain
            description: first plain line
              second plain line
        """)
        self.write_skill(skills, "multiline-single-directory", """
            name: 'multi-single'
            description: 'first single line
              second single line'
        """)
        self.write_skill(skills, "multiline-double-directory", r'''
            name: "multi-double"
            description: "first double line
              second\nline"
        ''')
        self.write_skill(skills, "comments-directory", """
            name: comments # ignored name comment
            description: plain value # ignored description comment
        """)
        self.write_skill(skills, "quoted-comment-directory", """
            name: "quoted-comment" # ignored trailing comment
            description: "kept # hash" # ignored trailing comment
        """)

        result = self.run_cli("show", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "alpha — plain description\n"
            "comments — plain value\n"
            "double — first second \"quoted\" and \\ slash\n"
            "folded — folded line next line\n"
            "literal — first line second line\n"
            "multi-double — first double line second line\n"
            "multi-plain — first plain line second plain line\n"
            "multi-single — first single line second single line\n"
            "o'brien — single 'quoted' description\n"
            "quoted-comment — kept # hash\n",
        )
        self.assertEqual(result.stderr, "")

    def test_show_reports_malformed_frontmatter_without_hiding_valid_siblings(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        invalid = {
            "alias-value": ("name: alias\ndescription: *shared\n", "unsupported"),
            "anchor-value": ("name: anchor\ndescription: &mark value\n", "unsupported"),
            "collection-value": ("name: collection\ndescription: [one, two]\n", "unsupported"),
            "duplicate-description": (
                "name: duplicate-description\ndescription: first\ndescription: second\n",
                "duplicate",
            ),
            "duplicate-name": (
                "name: first\nname: second\ndescription: duplicate name\n",
                "duplicate",
            ),
            "empty-description": ("name: empty-description\ndescription: ''\n", "empty"),
            "empty-name": ("name:\ndescription: empty name\n", "empty"),
            "escaped-surrogate": (
                'name: escaped-surrogate\ndescription: "\\uD800"\n',
                "unicode",
            ),
            "missing-description": ("name: missing-description\n", "missing"),
            "missing-name": ("description: missing name\n", "missing"),
            "nested-targets": (
                "metadata:\n  name: nested\n  description: not top level\n",
                "missing",
            ),
            "tag-value": ("name: tag\ndescription: !text tagged\n", "unsupported"),
            "unterminated-double": (
                'name: unterminated-double\ndescription: "not closed\n',
                "unterminated",
            ),
            "unterminated-single": (
                "name: unterminated-single\ndescription: 'not closed\n",
                "unterminated",
            ),
        }
        for directory, (metadata, _category) in invalid.items():
            self.write_skill(skills, directory, metadata)

        for directory, contents in {
            "malformed-delimiter": "----\nname: bad\ndescription: bad\n---\n",
            "missing-closing": "---\nname: bad\ndescription: bad\n",
            "no-delimiters": "name: bad\ndescription: bad\n",
        }.items():
            skill = skills / directory
            skill.mkdir()
            (skill / "SKILL.md").write_text(contents, encoding="utf-8")
            invalid[directory] = (contents, "frontmatter")

        invalid_utf = skills / "invalid-utf"
        invalid_utf.mkdir()
        invalid_utf.joinpath("SKILL.md").write_bytes(
            b"---\nname: invalid-utf\ndescription: \xff\n---\n"
        )
        invalid["invalid-utf"] = ("", "utf")
        (skills / "missing-skill-file").mkdir()
        invalid["missing-skill-file"] = ("", "missing")
        self.write_skill(skills, "valid-sibling-directory", """
            name: valid-sibling
            description: remains visible
        """)

        result = self.run_cli("show", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid-sibling — remains visible\n", result.stdout)
        for directory, (_contents, category) in invalid.items():
            with self.subTest(directory=directory):
                self.assert_invalid_show_entry(result.stdout, directory, category)
        displayed = [line.split(" — ", 1)[0] for line in result.stdout.splitlines()]
        self.assertEqual(displayed, sorted(displayed))

    def test_show_ignores_regular_files_and_never_follows_direct_skill_symlinks(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        (skills / "ordinary-file").write_text("not a skill\n", encoding="utf-8")
        (skills / "missing-skill-file").mkdir()
        self.write_skill(skills, "valid-directory", """
            name: valid
            description: direct real directory
        """)
        external = self.home / "external-skill"
        external.mkdir()
        external.joinpath("SKILL.md").write_text(
            "---\nname: external-secret\ndescription: must not be read\n---\n",
            encoding="utf-8",
        )
        (skills / "linked-directory").symlink_to(external, target_is_directory=True)
        linked_file = skills / "linked-skill-file"
        linked_file.mkdir()
        linked_file.joinpath("SKILL.md").symlink_to(external / "SKILL.md")

        result = self.run_cli("show", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid — direct real directory\n", result.stdout)
        self.assertNotIn("ordinary-file", result.stdout)
        self.assertNotIn("external-secret", result.stdout)
        self.assert_invalid_show_entry(result.stdout, "missing-skill-file", "missing")
        self.assert_invalid_show_entry(result.stdout, "linked-directory", "unsupported")
        self.assert_invalid_show_entry(result.stdout, "linked-skill-file", "unsupported")

    def test_show_rejects_missing_and_invalid_set_names(self):
        self.initialize()
        before = self.filesystem_snapshot(self.home)

        missing = self.run_cli("show", "missing")
        self.assert_refused(missing)
        for name in ("../escape", "Upper", ".hidden", "two words"):
            with self.subTest(name=name):
                result = self.run_cli("show", name)
                self.assert_refused(result)

        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_inspection_commands_reject_uninitialized_and_invalid_layouts_read_only(self):
        commands = (("list",), ("current",), ("show", "default"))
        for index, arguments in enumerate(commands):
            with self.subTest(layout="uninitialized", command=arguments[0]):
                home = self.new_home(f"inspection-uninitialized-{index}")
                root = home / ".agents"
                root.mkdir()
                (root / ".skillset.lock").write_text("", encoding="utf-8")
                before = self.filesystem_snapshot(home)
                result = self.run_cli(*arguments, home=home)
                self.assert_refused(result)
                self.assertEqual(self.filesystem_snapshot(home), before)

        def replace_link(path, target):
            path.unlink()
            path.symlink_to(target)

        mutations = {
            "skills-alias": lambda root: replace_link(
                root / "skills", "skillsets/default/skills"
            ),
            "lock-alias": lambda root: replace_link(
                root / ".skill-lock.json", "skillsets/default/.skill-lock.json"
            ),
            "active-target": lambda root: replace_link(
                root / "active", "skillsets/missing"
            ),
            "set-shape": lambda root: shutil.rmtree(
                root / "skillsets" / "default" / "skills"
            ),
            "lockfile": lambda root: (
                root / "skillsets" / "default" / ".skill-lock.json"
            ).write_text("not json\n", encoding="utf-8"),
        }
        case = 0
        for label, mutate in mutations.items():
            for arguments in commands:
                with self.subTest(layout=label, command=arguments[0]):
                    home = self.new_home(f"inspection-invalid-{case}")
                    case += 1
                    root = self.make_managed_layout(home)
                    (root / ".skillset.lock").write_text("", encoding="utf-8")
                    mutate(root)
                    before = self.filesystem_snapshot(home)
                    result = self.run_cli(*arguments, home=home)
                    self.assert_refused(result)
                    self.assertEqual(self.filesystem_snapshot(home), before)

    def test_successful_inspection_commands_are_strictly_read_only(self):
        self.initialize()
        self.make_set(self.root, "empty")
        skills = self.root / "skillsets" / "default" / "skills"
        self.write_skill(skills, "valid", """
            name: valid
            description: snapshot payload
        """)
        before = self.filesystem_snapshot(self.home)

        for arguments in (
            ("list",),
            ("list", "-v"),
            ("list", "--verbose"),
            ("current",),
            ("show", "default"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_each_inspection_command_waits_for_the_advisory_lock_without_blind_sleep(self):
        self.initialize()
        expected = {
            ("list",): "* default\n",
            ("current",): "default\n",
            ("show", "default"): "",
        }
        lock_path = self.root / ".skillset.lock"
        for index, (arguments, stdout_expected) in enumerate(expected.items()):
            with self.subTest(command=arguments[0]):
                attempted = self.sandbox / f"inspection-lock-attempted-{index}"
                fault = self.fault_environment(
                    f"""
                    import fcntl
                    from pathlib import Path
                    marker = Path({str(attempted)!r})
                    original_flock = fcntl.flock
                    def marked_flock(file, operation):
                        if operation & fcntl.LOCK_EX:
                            marker.write_text("attempted", encoding="utf-8")
                        return original_flock(file, operation)
                    fcntl.flock = marked_flock
                    """
                )
                process = None
                with lock_path.open("a+") as lock_file:
                    fcntl.flock(lock_file, fcntl.LOCK_EX)
                    process = self.popen_cli(*arguments, extra_environment=fault)
                    try:
                        self.wait_for_path(attempted, process)
                        self.assertIsNone(
                            process.poll(), f"{arguments} did not block on the lock"
                        )
                    finally:
                        fcntl.flock(lock_file, fcntl.LOCK_UN)
                try:
                    stdout, stderr = process.communicate(timeout=5)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=2)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
                self.assertEqual(stdout, stdout_expected)
                self.assertEqual(stderr, "")

    def test_skills_appends_global_to_scoped_upstream_commands(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        cases = (
            (("add", "owner/repository", "--skill", "alpha"),
             ["skills", "add", "owner/repository", "--skill", "alpha", "--global"]),
            (("list", "--json"), ["skills", "list", "--json", "--global"]),
            (("ls",), ["skills", "ls", "--global"]),
            (("remove", "alpha", "beta"),
             ["skills", "remove", "alpha", "beta", "--global"]),
            (("rm", "alpha"), ["skills", "rm", "alpha", "--global"]),
            (("update", "alpha"), ["skills", "update", "alpha", "--global"]),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                record.unlink(missing_ok=True)
                result = self.run_cli("skills", *arguments, extra_environment=environment)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assert_fake_argv(record, expected)

    def test_skills_preserves_existing_global_flags_without_adding_duplicates(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        cases = (
            (("add", "source", "-g", "--agent", "cursor"),
             ["skills", "add", "source", "-g", "--agent", "cursor"]),
            (("remove", "alpha", "--global"),
             ["skills", "remove", "alpha", "--global"]),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                record.unlink(missing_ok=True)
                result = self.run_cli("skills", *arguments, extra_environment=environment)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                payload = self.assert_fake_argv(record, expected)
                self.assertEqual(
                    sum(flag in ("-g", "--global") for flag in payload["argv"]), 1
                )

    def test_skills_rejects_project_scope_for_scoped_commands_without_child(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        for command in ("add", "list", "ls", "remove", "rm", "update"):
            for project_flag in ("-p", "--project"):
                with self.subTest(command=command, project_flag=project_flag):
                    record.unlink(missing_ok=True)
                    result = self.run_cli(
                        "skills", command, "alpha", project_flag,
                        extra_environment=environment,
                    )
                    self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))
                    self.assertIn("project", (result.stdout + result.stderr).lower())
                    self.assertFalse(record.exists(), "project scope invoked npx")

    def test_skills_passes_scope_free_and_empty_arguments_unchanged(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        cases = (
            ((), ["skills"]),
            (("-h",), ["skills", "-h"]),
            (("--help",), ["skills", "--help"]),
            (("find", "formatters", "--limit", "2"),
             ["skills", "find", "formatters", "--limit", "2"]),
            (("use", "alpha", "--agent", "cursor"),
             ["skills", "use", "alpha", "--agent", "cursor"]),
            (("init", "--yes"), ["skills", "init", "--yes"]),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                record.unlink(missing_ok=True)
                result = self.run_cli("skills", *arguments, extra_environment=environment)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assert_fake_argv(record, expected)

    def test_skills_passes_unknown_command_unchanged_with_scope_warning(self):
        self.initialize()
        environment, record = self.fake_npx_environment()

        result = self.run_cli(
            "skills", "future-command", "two words", "--option=value",
            extra_environment=environment,
        )

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assert_fake_argv(
            record, ["skills", "future-command", "two words", "--option=value"]
        )
        warning = result.stderr.lower()
        self.assertIn("warning", warning)
        self.assertIn("global", warning)
        self.assertIn("inject", warning)
        self.assertRegex(warning, r"\b(no|not|without)\b")

    def test_skills_preserves_arbitrary_argument_boundaries_and_order(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        arguments = ("add", "source with spaces", "", "--tag=a b", "--", "-literal")

        result = self.run_cli("skills", *arguments, extra_environment=environment)

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assert_fake_argv(
            record,
            ["skills", "add", "source with spaces", "", "--tag=a b", "--global", "--", "-literal"],
        )

    def test_skills_treats_scope_flags_after_option_terminator_as_literals(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        cases = (
            (
                ("add", "source", "--", "--global"),
                ["skills", "add", "source", "--global", "--", "--global"],
            ),
            (
                ("remove", "alpha", "--", "--project"),
                ["skills", "remove", "alpha", "--global", "--", "--project"],
            ),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                record.unlink(missing_ok=True)
                result = self.run_cli("skills", *arguments, extra_environment=environment)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assert_fake_argv(record, expected)

    def test_skills_removes_xdg_state_home_only_from_child_environment(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        sentinel = str(self.sandbox / "caller-xdg-state")
        environment["XDG_STATE_HOME"] = sentinel
        existed = "XDG_STATE_HOME" in os.environ
        original = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = sentinel
        try:
            result = self.run_cli("skills", "list", extra_environment=environment)
            self.assertEqual(os.environ.get("XDG_STATE_HOME"), sentinel)
        finally:
            if existed:
                os.environ["XDG_STATE_HOME"] = original
            else:
                os.environ.pop("XDG_STATE_HOME", None)

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        payload = self.assert_fake_argv(record, ["skills", "list", "--global"])
        self.assertFalse(payload["environment"]["XDG_STATE_HOME_present"])
        self.assertIsNone(payload["environment"]["XDG_STATE_HOME"])

    def test_skills_child_behaviorally_inherits_stdin_stdout_and_stderr(self):
        self.initialize()
        environment, _record = self.fake_npx_environment()
        environment["FAKE_NPX_ECHO_STDIN"] = "1"
        payload = "first line\nsecond line with spaces\n"

        result = self.run_cli(
            "skills", "find", "alpha",
            extra_environment=environment,
            input_text=payload,
        )

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(result.stdout, payload)
        self.assertEqual(result.stderr, payload)

    def test_skills_returns_exact_nonzero_upstream_status(self):
        self.initialize()
        environment, _record = self.fake_npx_environment()
        environment["FAKE_NPX_STATUS"] = "37"

        result = self.run_cli("skills", "find", "alpha", extra_environment=environment)

        self.assertEqual(result.returncode, 37, (result.stdout, result.stderr))

    def test_skills_signal_reaches_child_without_leaving_it_orphaned(self):
        self.initialize()
        environment, record = self.fake_npx_environment()
        ready = self.sandbox / "signal-child-ready"
        release = self.sandbox / "signal-child-release"
        received = self.sandbox / "signal-child-received"
        environment.update({
            "FAKE_NPX_READY": str(ready),
            "FAKE_NPX_WAIT_FOR": str(release),
            "FAKE_NPX_SIGNAL": str(received),
            "FAKE_NPX_SIGNAL_STATUS": "73",
        })
        process = self.popen_cli(
            "skills", "find", "alpha",
            extra_environment=environment,
            start_new_session=True,
        )
        try:
            self.wait_for_path(ready, process)
            child_pid = self.assert_fake_argv(
                record, ["skills", "find", "alpha"]
            )["pid"]
            os.killpg(os.getpgid(process.pid), signal.SIGINT)
            stdout, stderr = process.communicate(timeout=5)
            self.wait_for_path(received)
            self.assertEqual(int(received.read_text(encoding="utf-8")), signal.SIGINT)
            self.wait_for_pid_exit(child_pid)
        finally:
            if process.poll() is None:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.communicate(timeout=2)
        self.assertEqual(process.returncode, 73, (stdout, stderr))

    def test_skills_holds_advisory_lock_for_child_lifetime_and_blocks_management(self):
        self.initialize()
        environment, _record = self.fake_npx_environment()
        child_ready = self.sandbox / "locking-child-ready"
        child_release = self.sandbox / "locking-child-release"
        lock_attempted = self.sandbox / "management-lock-attempted"
        environment.update({
            "FAKE_NPX_READY": str(child_ready),
            "FAKE_NPX_WAIT_FOR": str(child_release),
        })
        delegated = self.popen_cli("skills", "list", extra_environment=environment)
        management = None
        try:
            self.wait_for_path(child_ready, delegated)
            with (self.root / ".skillset.lock").open("a+") as probe:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)

            fault = self.fault_environment(
                f"""
                import fcntl
                from pathlib import Path
                marker = Path({str(lock_attempted)!r})
                original_flock = fcntl.flock
                def marked_flock(file, operation):
                    if operation & fcntl.LOCK_EX:
                        marker.write_text("attempted", encoding="utf-8")
                    return original_flock(file, operation)
                fcntl.flock = marked_flock
                """
            )
            management = self.popen_cli(
                "create", "blocked", extra_environment=fault
            )
            self.wait_for_path(lock_attempted, management)
            self.assertIsNone(management.poll(), "management did not block on delegation")
            self.assertFalse((self.root / "skillsets" / "blocked").exists())

            child_release.write_text("release", encoding="utf-8")
            delegated_output = delegated.communicate(timeout=5)
            management_output = management.communicate(timeout=5)
            self.assertEqual(delegated.returncode, 0, delegated_output)
            self.assertEqual(management.returncode, 0, management_output)
            self.assertTrue((self.root / "skillsets" / "blocked").is_dir())
        finally:
            child_release.touch()
            for process in (delegated, management):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.communicate(timeout=2)

    def test_skills_refuses_uninitialized_and_invalid_layouts_without_child(self):
        uninitialized = self.new_home("delegation-uninitialized")
        environment, record = self.fake_npx_environment(uninitialized)
        result = self.run_cli(
            "skills", "list", home=uninitialized, extra_environment=environment
        )
        self.assert_refused(result)
        self.assertFalse(record.exists(), "uninitialized delegation invoked npx")

        def replace_link(path, target):
            path.unlink()
            path.symlink_to(target)

        mutations = {
            "skills-alias": lambda root: replace_link(
                root / "skills", "skillsets/default/skills"
            ),
            "lock-alias": lambda root: replace_link(
                root / ".skill-lock.json", "skillsets/default/.skill-lock.json"
            ),
            "active-target": lambda root: replace_link(
                root / "active", "skillsets/missing"
            ),
            "set-shape": lambda root: shutil.rmtree(
                root / "skillsets" / "default" / "skills"
            ),
            "lockfile": lambda root: (
                root / "skillsets" / "default" / ".skill-lock.json"
            ).write_text("not json\n", encoding="utf-8"),
        }
        for index, (label, mutate) in enumerate(mutations.items()):
            with self.subTest(layout=label):
                home = self.new_home(f"delegation-invalid-{index}")
                root = self.make_managed_layout(home)
                mutate(root)
                environment, record = self.fake_npx_environment(home)
                result = self.run_cli(
                    "skills", "list", home=home, extra_environment=environment
                )
                self.assert_refused(result)
                self.assertFalse(record.exists(), f"{label} invoked npx")

    def test_argparse_usage_errors_exit_two(self):
        cases = [
            (),
            ("init",),
            ("init", "default", "extra"),
            ("create",),
            ("create", "copy", "--from"),
            ("use",),
            ("list", "extra"),
            ("list", "--unknown"),
            ("current", "extra"),
            ("current", "--verbose"),
            ("show",),
            ("show", "default", "extra"),
            ("unknown-command",),
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 2, (result.stdout, result.stderr))

    def test_invalid_names_are_operational_errors_and_cannot_escape_skillsets(self):
        invalid_names = ["../escape", "a/b", ".hidden", "Upper", "two words", "-lead", "_lead"]
        for index, name in enumerate(invalid_names):
            home = self.new_home(f"invalid-init-{index}")
            result = self.run_cli("init", name, home=home)
            with self.subTest(command="init", name=name):
                self.assert_refused(result)
                candidate = home / ".agents" / "skillsets" / name
                self.assertFalse(candidate.exists())

        self.initialize()
        for command in ("create", "use"):
            for name in invalid_names:
                with self.subTest(command=command, name=name):
                    result = self.run_cli(command, name)
                    self.assert_refused(result)
                    if command == "create":
                        self.assertFalse((self.root / "skillsets" / name).exists())
        result = self.run_cli("create", "copy", "--from", "../default")
        self.assert_refused(result)
        self.assertFalse((self.root / "skillsets" / "copy").exists())

    def test_init_from_empty_state_creates_exact_layout(self):
        result = self.run_cli("init", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_aliases(self.root, "default")
        self.assert_empty_set(self.root, "default")
        self.assertTrue((self.root / ".skillset.lock").is_file())

    def test_init_adopts_existing_skills_and_version_three_lock_without_rewriting(self):
        source_skills = self.root / "skills"
        (source_skills / "alpha" / "nested").mkdir(parents=True)
        (source_skills / "alpha" / "SKILL.md").write_bytes(b"skill contents\n")
        (source_skills / "alpha" / "nested" / "data.bin").write_bytes(b"\x00\x01")
        lock_text = '{\n  "version": 3,\n  "skills": {},\n  "dismissed": {}\n}\n'
        self.write_lock(self.root / ".skill-lock.json", raw=lock_text)

        result = self.run_cli("init", "baseline")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_aliases(self.root, "baseline")
        adopted = self.root / "skillsets" / "baseline"
        self.assertEqual((adopted / "skills" / "alpha" / "SKILL.md").read_bytes(), b"skill contents\n")
        self.assertEqual((adopted / "skills" / "alpha" / "nested" / "data.bin").read_bytes(), b"\x00\x01")
        self.assertEqual((adopted / ".skill-lock.json").read_text(encoding="utf-8"), lock_text)

    def test_init_with_only_existing_skills_creates_empty_lock(self):
        (self.root / "skills" / "alpha").mkdir(parents=True)
        (self.root / "skills" / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")

        result = self.run_cli("init", "mixed")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "skills" / "alpha" / "SKILL.md").read_text(), "alpha\n")
        self.assertEqual(json.loads((self.root / ".skill-lock.json").read_text()), EMPTY_LOCK)

    def test_init_with_only_existing_lock_creates_empty_skills(self):
        self.write_lock(self.root / ".skill-lock.json")

        result = self.run_cli("init", "mixed")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list((self.root / "skills").iterdir()), [])
        self.assertEqual(json.loads((self.root / ".skill-lock.json").read_text()), EMPTY_LOCK)

    def test_init_rejects_invalid_existing_lock_without_moving_state(self):
        (self.root / "skills" / "alpha").mkdir(parents=True)
        lock = self.root / ".skill-lock.json"
        self.write_lock(lock, {"version": 2, "skills": {}, "dismissed": {}})

        result = self.run_cli("init", "default")

        self.assert_refused(result)
        self.assertTrue((self.root / "skills" / "alpha").is_dir())
        self.assertFalse((self.root / "skills").is_symlink())
        self.assertEqual(json.loads(lock.read_text()), {"version": 2, "skills": {}, "dismissed": {}})
        self.assertFalse((self.root / "skillsets" / "default").exists())

    def test_init_rejects_unmanaged_root_symlinks(self):
        for index, entry in enumerate(("skills", ".skill-lock.json")):
            home = self.new_home(f"unmanaged-link-{index}")
            root = home / ".agents"
            root.mkdir()
            external = home / "external"
            if entry == "skills":
                external.mkdir()
            else:
                self.write_lock(external)
            (root / entry).symlink_to(external)

            result = self.run_cli("init", "default", home=home)

            with self.subTest(entry=entry):
                self.assert_refused(result)
                self.assertTrue((root / entry).is_symlink())
                self.assertEqual(Path(os.readlink(root / entry)), external)
                self.assertFalse((root / "skillsets" / "default").exists())

    def test_init_rejects_partial_managed_layouts(self):
        for index, entry in enumerate(("skillsets", "active")):
            home = self.new_home(f"partial-{index}")
            root = home / ".agents"
            root.mkdir()
            if entry == "skillsets":
                (root / entry).mkdir()
            else:
                (root / entry).symlink_to("skillsets/default")

            result = self.run_cli("init", "default", home=home)

            with self.subTest(entry=entry):
                self.assert_refused(result)
                self.assertTrue(os.path.lexists(root / entry))

    def test_init_refuses_target_collision_and_reinitialization(self):
        (self.root / "skillsets" / "default").mkdir(parents=True)
        marker = self.root / "skillsets" / "default" / "keep"
        marker.write_text("untouched", encoding="utf-8")
        result = self.run_cli("init", "default")
        self.assert_refused(result)
        self.assertEqual(marker.read_text(), "untouched")

        other_home = self.new_home("already-managed")
        self.initialize(home=other_home)
        result = self.run_cli("init", "again", home=other_home)
        self.assert_refused(result)
        self.assertFalse((other_home / ".agents" / "skillsets" / "again").exists())

    def test_create_empty_set_without_changing_active_set(self):
        self.initialize()
        active_before = os.readlink(self.root / "active")

        result = self.run_cli("create", "experiment")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_empty_set(self.root, "experiment")
        self.assertEqual(os.readlink(self.root / "active"), active_before)

    def test_create_from_clones_complete_state_exactly(self):
        self.initialize()
        source = self.root / "skillsets" / "default"
        skill = source / "skills" / "alpha"
        skill.mkdir()
        executable = skill / "tool"
        executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        executable.chmod(0o751)
        (skill / "tool-link").symlink_to("tool")
        lock_bytes = b'{"version":3,"skills":{},"dismissed":{}}\n'
        (source / ".skill-lock.json").write_bytes(lock_bytes)

        result = self.run_cli("create", "clone", "--from", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        clone = self.root / "skillsets" / "clone"
        self.assertEqual((clone / "skills" / "alpha" / "tool").read_bytes(), executable.read_bytes())
        self.assertEqual(stat.S_IMODE((clone / "skills" / "alpha" / "tool").stat().st_mode), 0o751)
        self.assertTrue((clone / "skills" / "alpha" / "tool-link").is_symlink())
        self.assertEqual(os.readlink(clone / "skills" / "alpha" / "tool-link"), "tool")
        self.assertEqual((clone / ".skill-lock.json").read_bytes(), lock_bytes)
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/default")

    def test_create_refuses_regular_and_symlink_target_collisions(self):
        regular_home = self.new_home("regular-collision")
        regular_root = self.make_managed_layout(regular_home)
        regular = self.make_set(regular_root, "occupied")
        marker = regular / "skills" / "keep"
        marker.write_text("keep", encoding="utf-8")
        result = self.run_cli("create", "occupied", home=regular_home)
        self.assert_refused(result)
        self.assertEqual(marker.read_text(), "keep")

        linked_home = self.new_home("symlink-collision")
        linked_root = self.make_managed_layout(linked_home)
        external = linked_home / "external-set"
        (external / "skills").mkdir(parents=True)
        self.write_lock(external / ".skill-lock.json")
        marker = external / "skills" / "keep"
        marker.write_text("untouched", encoding="utf-8")
        (linked_root / "skillsets" / "linked").symlink_to(external)
        result = self.run_cli("create", "linked", home=linked_home)
        self.assert_refused(result)
        self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")

    def test_create_from_refuses_missing_incomplete_and_symlink_sources(self):
        for index, source in enumerate(("missing", "incomplete", "linked")):
            home = self.new_home(f"invalid-source-{index}")
            root = self.make_managed_layout(home)
            if source == "incomplete":
                (root / "skillsets" / source / "skills").mkdir(parents=True)
            elif source == "linked":
                external = home / "external-source"
                (external / "skills").mkdir(parents=True)
                self.write_lock(external / ".skill-lock.json")
                (root / "skillsets" / source).symlink_to(external)
            target = f"copy-{index}"
            with self.subTest(source=source):
                result = self.run_cli("create", target, "--from", source, home=home)
                self.assert_refused(result)
                self.assertFalse((root / "skillsets" / target).exists())

    def test_create_and_use_refuse_before_initialization(self):
        for command, name in (("create", "new"), ("use", "new")):
            home = self.new_home(f"pre-init-{command}")
            result = self.run_cli(command, name, home=home)
            with self.subTest(command=command):
                self.assert_refused(result)
                self.assertFalse((home / ".agents" / "skillsets" / "new").exists())

    def test_create_and_use_refuse_invalid_managed_layouts(self):
        def replace_link(path, target):
            path.unlink()
            path.symlink_to(target)

        mutations = {
            "noncanonical-skills-alias": lambda root: replace_link(
                root / "skills", "skillsets/default/skills"
            ),
            "noncanonical-lock-alias": lambda root: replace_link(
                root / ".skill-lock.json", "skillsets/default/.skill-lock.json"
            ),
            "absolute-active-alias": lambda root: replace_link(
                root / "active", str(root / "skillsets" / "default")
            ),
            "missing-active-target": lambda root: replace_link(
                root / "active", "skillsets/missing"
            ),
            "missing-set-skills": lambda root: shutil.rmtree(
                root / "skillsets" / "default" / "skills"
            ),
            "malformed-set-lock": lambda root: (
                root / "skillsets" / "default" / ".skill-lock.json"
            ).write_text("not json\n", encoding="utf-8"),
        }
        for index, (label, mutate) in enumerate(mutations.items()):
            home = self.new_home(f"invalid-layout-{index}")
            root = self.make_managed_layout(home)
            mutate(root)
            for command, name in (("create", "new"), ("use", "default")):
                with self.subTest(layout=label, command=command):
                    result = self.run_cli(command, name, home=home)
                    self.assert_refused(result)
            self.assertFalse((root / "skillsets" / "new").exists())

    def test_use_refuses_missing_broken_and_symlink_targets_without_switching(self):
        names = (
            "missing",
            "linked",
            "no-skills",
            "no-lock",
            "bad-lock",
            "linked-skills",
            "linked-lock",
        )
        for index, name in enumerate(names):
            home = self.new_home(f"invalid-use-target-{index}")
            root = self.make_managed_layout(home)
            target = root / "skillsets" / name
            if name == "linked":
                external = home / "external-target"
                (external / "skills").mkdir(parents=True)
                self.write_lock(external / ".skill-lock.json")
                target.symlink_to(external)
            elif name == "no-skills":
                target.mkdir()
                self.write_lock(target / ".skill-lock.json")
            elif name == "no-lock":
                (target / "skills").mkdir(parents=True)
            elif name == "bad-lock":
                (target / "skills").mkdir(parents=True)
                self.write_lock(target / ".skill-lock.json", raw="{broken\n")
            elif name == "linked-skills":
                target.mkdir()
                (target / "skills").symlink_to(home)
                self.write_lock(target / ".skill-lock.json")
            elif name == "linked-lock":
                (target / "skills").mkdir(parents=True)
                (target / ".skill-lock.json").symlink_to(
                    root / "skillsets" / "default" / ".skill-lock.json"
                )
            with self.subTest(name=name):
                result = self.run_cli("use", name, home=home)
                self.assert_refused(result)
                self.assertEqual(os.readlink(root / "active"), "skillsets/default")

    def test_use_atomically_changes_only_active_alias(self):
        self.initialize()
        self.run_cli("create", "experiment")
        stable = {
            name: ((self.root / name).lstat().st_ino, os.readlink(self.root / name))
            for name in ("skills", ".skill-lock.json")
        }

        first = self.run_cli("use", "experiment")
        second = self.run_cli("use", "default")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/default")
        for name, identity in stable.items():
            self.assertEqual(((self.root / name).lstat().st_ino, os.readlink(self.root / name)), identity)

    def test_failed_atomic_use_keeps_previous_active_set_and_aliases(self):
        self.initialize()
        self.run_cli("create", "experiment")
        root = str(self.root)
        fault = self.fault_environment(
            f"""
            import os
            target = {str(self.root / 'active')!r}
            original_replace = os.replace
            original_rename = os.rename
            def fail_at_active(source, destination, *args, **kwargs):
                if os.path.abspath(os.fspath(destination)) == target:
                    raise OSError("injected active replacement failure")
                return original_replace(source, destination, *args, **kwargs)
            def fail_rename_at_active(source, destination, *args, **kwargs):
                if os.path.abspath(os.fspath(destination)) == target:
                    raise OSError("injected active replacement failure")
                return original_rename(source, destination, *args, **kwargs)
            os.replace = fail_at_active
            os.rename = fail_rename_at_active
            """
        )
        aliases_before = {name: os.readlink(self.root / name) for name in ("active", "skills", ".skill-lock.json")}

        result = self.run_cli("use", "experiment", extra_environment=fault)

        self.assert_refused(result)
        self.assertEqual(
            {name: os.readlink(self.root / name) for name in aliases_before}, aliases_before
        )
        root_symlinks = {path.name for path in self.root.iterdir() if path.is_symlink()}
        self.assertEqual(root_symlinks, {"active", "skills", ".skill-lock.json"})
        self.assertTrue((Path(root) / "skillsets" / "experiment").is_dir())

    def test_every_management_operation_waits_for_advisory_lock(self):
        self.root.mkdir()

        def run_while_locked(*arguments):
            lock_path = self.root / ".skillset.lock"
            with lock_path.open("a+") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                process = self.popen_cli(*arguments)
                try:
                    time.sleep(0.2)
                    self.assertIsNone(process.poll(), f"{arguments} did not wait for the lock")
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
                stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, (stdout, stderr))

        run_while_locked("init", "default")
        run_while_locked("create", "experiment")
        run_while_locked("use", "experiment")

    def test_interrupted_create_staging_is_refused_on_retry(self):
        self.initialize()
        marker = self.sandbox / "staging-path"
        destination = str(self.root / "skillsets" / "clone")
        fault = self.fault_environment(
            f"""
            import os
            import time
            from pathlib import Path
            destination = {destination!r}
            marker = Path({str(marker)!r})
            original_replace = os.replace
            original_rename = os.rename
            def stall_replace(source, target, *args, **kwargs):
                if os.path.abspath(os.fspath(target)) == destination:
                    marker.write_text(os.fspath(source), encoding="utf-8")
                    time.sleep(60)
                return original_replace(source, target, *args, **kwargs)
            def stall_rename(source, target, *args, **kwargs):
                if os.path.abspath(os.fspath(target)) == destination:
                    marker.write_text(os.fspath(source), encoding="utf-8")
                    time.sleep(60)
                return original_rename(source, target, *args, **kwargs)
            os.replace = stall_replace
            os.rename = stall_rename
            """
        )
        process = self.popen_cli("create", "clone", "--from", "default", extra_environment=fault)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if not marker.exists():
                if process.poll() is None:
                    self.fail("create did not reach atomic staging placement")
                self.fail(f"create exited before staging placement: {process.communicate()}")
            staging = Path(marker.read_text(encoding="utf-8"))
            if not staging.is_absolute():
                staging = self.home / staging
            process.kill()
            process.communicate(timeout=2)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)

        self.assertTrue(os.path.lexists(staging))
        result = self.run_cli("create", "clone", "--from", "default")
        self.assert_refused(result)
        self.assertTrue(os.path.lexists(staging))
        self.assertFalse((self.root / "skillsets" / "clone").exists())
        self.assertIn(str(staging), result.stdout + result.stderr)

    def test_init_rolls_back_after_keyboard_interrupt(self):
        (self.root / "skills" / "alpha").mkdir(parents=True)
        payload = b"original skill\n"
        (self.root / "skills" / "alpha" / "SKILL.md").write_bytes(payload)
        lock_bytes = b'{"version": 3, "skills": {}, "dismissed": {}}\n'
        (self.root / ".skill-lock.json").write_bytes(lock_bytes)
        fault = self.fault_environment(
            f"""
            import os
            destination = {str(self.root / 'active')!r}
            original_symlink = os.symlink
            def interrupt_alias(source, target, *args, **kwargs):
                if os.path.abspath(os.fspath(target)) == destination:
                    original_symlink(source, target, *args, **kwargs)
                    raise KeyboardInterrupt
                return original_symlink(source, target, *args, **kwargs)
            os.symlink = interrupt_alias
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "skills").is_symlink())
        self.assertEqual((self.root / "skills" / "alpha" / "SKILL.md").read_bytes(), payload)
        self.assertFalse((self.root / ".skill-lock.json").is_symlink())
        self.assertEqual((self.root / ".skill-lock.json").read_bytes(), lock_bytes)
        self.assertFalse(os.path.lexists(self.root / "active"))
        self.assertFalse((self.root / "skillsets" / "default").exists())

    def test_init_rolls_back_after_recoverable_alias_failure(self):
        (self.root / "skills" / "alpha").mkdir(parents=True)
        payload = b"original skill\n"
        (self.root / "skills" / "alpha" / "SKILL.md").write_bytes(payload)
        lock_bytes = b'{"version": 3, "skills": {}, "dismissed": {}}\n'
        (self.root / ".skill-lock.json").write_bytes(lock_bytes)
        fault = self.fault_environment(
            f"""
            import os
            destination = {str(self.root / '.skill-lock.json')!r}
            original_symlink = os.symlink
            def fail_lock_alias(source, target, *args, **kwargs):
                if os.path.abspath(os.fspath(target)) == destination:
                    raise OSError("injected alias failure")
                return original_symlink(source, target, *args, **kwargs)
            os.symlink = fail_lock_alias
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        self.assertFalse((self.root / "skills").is_symlink())
        self.assertEqual((self.root / "skills" / "alpha" / "SKILL.md").read_bytes(), payload)
        self.assertFalse((self.root / ".skill-lock.json").is_symlink())
        self.assertEqual((self.root / ".skill-lock.json").read_bytes(), lock_bytes)
        self.assertFalse(os.path.lexists(self.root / "active"))
        self.assertFalse((self.root / "skillsets" / "default").exists())

    def test_init_rollback_failure_reports_concrete_recovery_paths(self):
        (self.root / "skills" / "alpha").mkdir(parents=True)
        self.write_lock(self.root / ".skill-lock.json")
        original_skills = str(self.root / "skills")
        original_lock = str(self.root / ".skill-lock.json")
        staged_set = str(self.root / "skillsets" / "default")
        fault = self.fault_environment(
            f"""
            import os
            import shutil
            alias = {original_lock!r}
            rollback_targets = {{{original_skills!r}, {original_lock!r}}}
            failed = False
            original_symlink = os.symlink
            original_rename = os.rename
            original_replace = os.replace
            original_move = shutil.move
            def fail_alias(source, target, *args, **kwargs):
                global failed
                if os.path.abspath(os.fspath(target)) == alias:
                    failed = True
                    raise OSError("injected alias failure")
                return original_symlink(source, target, *args, **kwargs)
            def refuse_rollback(function, source, target, *args, **kwargs):
                if failed and os.path.abspath(os.fspath(target)) in rollback_targets:
                    raise OSError("injected rollback failure")
                return function(source, target, *args, **kwargs)
            os.symlink = fail_alias
            os.rename = lambda source, target, *args, **kwargs: refuse_rollback(
                original_rename, source, target, *args, **kwargs
            )
            os.replace = lambda source, target, *args, **kwargs: refuse_rollback(
                original_replace, source, target, *args, **kwargs
            )
            shutil.move = lambda source, target, *args, **kwargs: refuse_rollback(
                original_move, source, target, *args, **kwargs
            )
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        report = result.stdout + result.stderr
        self.assertIn(original_skills, report)
        self.assertIn(original_lock, report)
        self.assertIn(staged_set, report)


if __name__ == "__main__":
    unittest.main()