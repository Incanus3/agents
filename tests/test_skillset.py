import fcntl
import json
import os
import re
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

    def run_cli(self, *arguments, home=None, extra_environment=None, timeout=5):
        return subprocess.run(
            [str(SKILLSET), *arguments],
            cwd=home or self.home,
            env=self.environment(home, extra_environment),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def popen_cli(self, *arguments, home=None, extra_environment=None):
        return subprocess.Popen(
            [str(SKILLSET), *arguments],
            cwd=home or self.home,
            env=self.environment(home, extra_environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

    def fault_environment(self, source):
        directory = self.sandbox / f"fault-{len(list(self.sandbox.glob('fault-*')))}"
        directory.mkdir()
        (directory / "sitecustomize.py").write_text(
            textwrap.dedent(source), encoding="utf-8"
        )
        return {"PYTHONPATH": str(directory)}

    def assert_refused(self, result):
        self.assertEqual(result.returncode, 1, (result.stdout, result.stderr))

    def test_help_exposes_only_bead_one_commands(self):
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        command_group = re.search(r"\{([^}]+)\}", result.stdout)
        self.assertIsNotNone(command_group, result.stdout)
        self.assertEqual(set(command_group.group(1).split(",")), {"init", "create", "use"})

    def test_argparse_usage_errors_exit_two(self):
        cases = [
            (),
            ("init",),
            ("init", "default", "extra"),
            ("create",),
            ("create", "copy", "--from"),
            ("use",),
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