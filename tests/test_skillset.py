import errno
import fcntl
import json
import os
import re
import signal
import shutil
import stat
import struct
import subprocess
import tempfile
import termios
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
        cwd=None,
        extra_environment=None,
        input_text=None,
        timeout=5,
    ):
        return subprocess.run(
            [str(SKILLSET), *arguments],
            cwd=cwd or home or self.home,
            env=self.environment(home, extra_environment),
            text=True,
            input=input_text,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def run_cli_tty(
        self, *arguments, cwd=None, extra_environment=None, terminal_columns=None
    ):
        environment = self.environment()
        environment.pop("NO_COLOR", None)
        environment["TERM"] = "xterm-256color"
        if extra_environment:
            environment.update(extra_environment)
        master, slave = os.openpty()
        if terminal_columns is not None:
            dimensions = struct.pack("HHHH", 24, terminal_columns, 0, 0)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, dimensions)
        process = subprocess.Popen(
            [str(SKILLSET), *arguments],
            cwd=cwd or self.home,
            env=environment,
            stdout=slave,
            stderr=subprocess.PIPE,
            text=False,
        )
        os.close(slave)
        chunks = []
        try:
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)
            _stdout, stderr = process.communicate(timeout=5)
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
        stdout = b"".join(chunks).decode("utf-8").replace("\r\n", "\n")
        return subprocess.CompletedProcess(
            process.args, process.returncode, stdout, stderr.decode("utf-8")
        )

    def popen_cli(
        self,
        *arguments,
        home=None,
        extra_environment=None,
        start_new_session=False,
        stdin=None,
    ):
        return subprocess.Popen(
            [str(SKILLSET), *arguments],
            cwd=home or self.home,
            env=self.environment(home, extra_environment),
            text=True,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=start_new_session,
        )

    def write_lock(self, path, value=EMPTY_LOCK, *, raw=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = raw if raw is not None else json.dumps(value) + "\n"
        path.write_text(data, encoding="utf-8")

    def write_config(self, home, source, value=None, *, raw=None):
        root = home / ".agents"
        root.mkdir(parents=True, exist_ok=True)
        config = root / "config.json"
        data = (
            raw
            if raw is not None
            else json.dumps(
                value
                if value is not None
                else {"version": 1, "skillsets_directory": str(source)}
            )
            + "\n"
        )
        config.write_text(data, encoding="utf-8")
        return config

    def make_set(self, root, name, lock=EMPTY_LOCK):
        skillset = root / "skillsets" / name
        (skillset / "skills").mkdir(parents=True)
        self.write_lock(skillset / ".skill-lock.json", lock)
        return skillset

    def make_manual_set(self, root, name):
        skillset = root / "skillsets" / name
        (skillset / "skills").mkdir(parents=True)
        (skillset / ".skillset-manual").touch()
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

    def tree_contract_snapshot(self, root):
        return {
            relative: (metadata[0], metadata[1], metadata[3], metadata[6])
            for relative, metadata in self.filesystem_snapshot(root).items()
        }

    def show_rows(self, output):
        lines = output.splitlines()
        self.assertGreaterEqual(len(lines), 2, output)
        self.assertIn("|", lines[0])
        return [tuple(cell.strip() for cell in line.split("|", 1)) for line in lines[2:]]

    def assert_invalid_show_entry(self, output, directory, category):
        matches = [row for row in self.show_rows(output) if row[0] == directory]
        self.assertEqual(len(matches), 1, (directory, output))
        self.assertIn(category.lower(), matches[0][1].lower())

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

    def doctor_findings(self, result, severity):
        prefix = f"skillset: {severity}:"
        self.assertNotIn(prefix, result.stdout)
        for line in result.stderr.splitlines():
            if line:
                self.assertTrue(
                    line.startswith(("skillset: error:", "skillset: warning:")),
                    line,
                )
        return [
            line for line in result.stderr.splitlines() if line.startswith(prefix)
        ]

    def assert_finding_line(self, lines, *fragments):
        lowered = [line.lower() for line in lines]
        expected = tuple(str(fragment).lower() for fragment in fragments)
        matches = [
            line for line in lowered if all(fragment in line for fragment in expected)
        ]
        self.assertEqual(len(matches), 1, (expected, lines))

    def assert_uninitialized_doctor_findings(self, result, root):
        errors = self.doctor_findings(result, "error")
        expected = (
            (root / ".skillset.lock", "lock", "missing"),
            (root / "skills", "alias", "missing"),
            (root / ".skill-lock.json", "alias", "missing"),
            (root / "active", "active", "missing"),
            (root / "skillsets", "skillsets", "missing"),
        )
        for fragments in expected:
            with self.subTest(finding=fragments):
                self.assert_finding_line(errors, *fragments)
        self.assertGreaterEqual(len(errors), len(expected))
        return errors

    def assert_no_doctor_findings(self, result):
        output = result.stdout + result.stderr
        self.assertNotIn("skillset: error:", output)
        self.assertNotIn("skillset: warning:", output)

    def test_help_includes_exact_supported_commands(self):
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("create a skillset", result.stdout)
        self.assertNotIn("create an inactive skillset", result.stdout)
        command_group = re.search(r"\{([^}]+)\}", result.stdout)
        self.assertIsNotNone(command_group, result.stdout)
        self.assertEqual(
            set(command_group.group(1).split(",")),
            {
                "init",
                "create",
                "use",
                "rename",
                "remove",
                "codex",
                "skills",
                "list",
                "current",
                "show",
                "doctor",
                "completions",
            },
        )

    def test_completions_emit_deterministic_scripts_without_managed_state(self):
        before = self.filesystem_snapshot(self.home)
        for shell in ("bash", "zsh", "fish"):
            with self.subTest(shell=shell):
                first = self.run_cli("completions", shell)
                second = self.run_cli("completions", shell)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(first.stderr, "")
                self.assertEqual(first.stdout, second.stdout)
                self.assertTrue(first.stdout.strip())
                self.assertTrue(first.stdout.endswith("\n"))
                self.assertFalse(first.stdout.endswith("\n\n"))
                self.assertIn("skillset", first.stdout)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_completions_bypass_malformed_managed_state_without_mutation(self):
        self.root.mkdir()
        (self.root / "active").write_text(
            "not a managed symlink", encoding="utf-8"
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("completions", "bash")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("complete", result.stdout)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_completion_scripts_include_the_complete_wrapper_grammar(self):
        commands = (
            "init", "create", "use", "rename", "remove", "list",
            "codex", "current", "show", "doctor", "skills", "completions",
        )
        for shell in ("bash", "zsh", "fish"):
            with self.subTest(shell=shell):
                script = self.run_cli("completions", shell).stdout
                for command in commands:
                    self.assertIn(command, script)
                options = (
                    ("-l help", "-l from", "-l use", "-l yes", "-l verbose", "-l fix")
                    if shell == "fish"
                    else ("--help", "--from", "--use", "--yes", "--verbose", "--fix")
                )
                for option in options:
                    self.assertIn(option, script)
                self.assertIn("skillset list", script)
                self.assertIn("2>/dev/null", script)

    def test_zsh_completion_uses_stateful_nested_parser_contract(self):
        generated = self.run_cli("completions", "zsh")

        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual(generated.stderr, "")
        script = generated.stdout
        self.assertIn('case "${words[1]}" in', script)
        self.assertNotIn('case "${words[2]}" in', script)
        self.assertIn("{-f,--from=}'[clone from an existing skillset]", script)
        self.assertNotIn("{-f,--from}'[clone from an existing skillset]", script)
        outer_parser, nested_parsers = script.split('case "${words[1]}" in', 1)
        self.assertIn("_arguments -S -C \\", outer_parser)
        self.assertEqual(outer_parser.count("_arguments"), 1)
        self.assertEqual(nested_parsers.count("_arguments"), 12)
        self.assertEqual(nested_parsers.count("_arguments -S"), 12)
        self.assertEqual(script.count("_arguments"), 13)
        self.assertEqual(script.count("_arguments -S"), 13)
        self.assertEqual(script.count("_arguments -S -C"), 1)
        self.assertIn('-A "-*"', outer_parser)
        self.assertEqual(nested_parsers.count("&& return 0"), 12)
        self.assertIn("skills) return 0 ;;", script)
        self.assertIn(
            'if [[ "${zsh_eval_context[-1]}" == loadautofunc ]]; then',
            script,
        )
        self.assertIn('_skillset "$@"', script)
        self.assertIn("else\n    compdef _skillset skillset\nfi", script)

    def test_bash_completion_is_contextual_and_uses_managed_names(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        self.initialize()
        self.make_set(self.root, "demo")
        generated = self.run_cli("completions", "bash")
        script = self.sandbox / "skillset.bash"
        script.write_text(generated.stdout, encoding="utf-8")
        environment = self.environment(
            extra={"PATH": f"{REPOSITORY_ROOT / 'bin'}:{os.environ.get('PATH', '')}"}
        )
        probe = r'''source "$1"
COMP_WORDS=(skillset sh); COMP_CWORD=1; _skillset_completion
printf 'top:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset use d); COMP_CWORD=2; _skillset_completion
printf 'use:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset create --from=d); COMP_CWORD=2; _skillset_completion
printf 'from:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset create --from = d); COMP_CWORD=4; _skillset_completion
printf 'from-split:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset create --from =); COMP_CWORD=3; _skillset_completion skillset '' --from
printf 'from-empty:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset create --from d); COMP_CWORD=3; _skillset_completion
printf 'from-separated:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset rename default n); COMP_CWORD=3; _skillset_completion
printf 'new:%s\n' "${#COMPREPLY[@]}"
COMP_WORDS=(skillset use -- -); COMP_CWORD=3; _skillset_completion
printf 'terminator:%s\n' "${#COMPREPLY[@]}"
COMP_WORDS=(skillset skills l); COMP_CWORD=2; _skillset_completion
printf 'skills:%s\n' "${#COMPREPLY[@]}"
COMP_WORDS=(skillset codex e); COMP_CWORD=2; _skillset_completion
printf 'codex-command:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset codex enable d); COMP_CWORD=3; _skillset_completion
printf 'codex-enable:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset codex enable --local d); COMP_CWORD=4; _skillset_completion
printf 'codex-local-enable:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset codex list --v); COMP_CWORD=3; _skillset_completion
printf 'codex-list:%s\n' "${COMPREPLY[*]}"'''
        result = subprocess.run(
            [bash, "-c", probe, "bash", str(script)],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "top:show", "use:default demo",
                "from:--from=default --from=demo",
                "from-split:default demo", "from-empty:default demo",
                "from-separated:default demo", "new:0",
                "terminator:0", "skills:0", "codex-command:enable",
                "codex-enable:default demo", "codex-local-enable:default demo",
                "codex-list:--verbose",
            ],
        )

    def test_fish_completion_is_contextual_and_uses_managed_names(self):
        fish = shutil.which("fish")
        if fish is None:
            self.skipTest("fish is not installed")
        self.initialize()
        self.make_set(self.root, "demo")
        generated = self.run_cli("completions", "fish")
        script = self.sandbox / "skillset.fish"
        script.write_text(generated.stdout, encoding="utf-8")
        environment = self.environment(extra={
            "PATH": f"{REPOSITORY_ROOT / 'bin'}:{os.environ.get('PATH', '')}"
        })

        def candidates(commandline):
            result = subprocess.run(
                [fish, "-c", "source $argv[1]; complete -C $argv[2]", str(script), commandline],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return [line.split("\t", 1)[0] for line in result.stdout.splitlines()]

        self.assertIn("show", candidates("skillset sh"))
        self.assertEqual(candidates("skillset use d"), ["default", "demo"])
        self.assertEqual(candidates("skillset create --from d"), ["default", "demo"])
        self.assertIn("commandline -xpc", generated.stdout)
        self.assertNotIn("commandline -opc", generated.stdout)
        self.assertEqual(candidates("skillset rename default n"), [])
        self.assertEqual(candidates("skillset skills l"), [])
        self.assertEqual(candidates("skillset codex e"), ["enable"])
        self.assertEqual(candidates("skillset codex enable d"), ["default", "demo"])
        self.assertEqual(candidates("skillset codex list --v"), ["--verbose"])

    def test_completion_name_lookup_discards_stdout_on_failure(self):
        stub_directory = self.sandbox / "failed-list-bin"
        stub_directory.mkdir()
        stub = stub_directory / "skillset"
        stub.write_text(
            "#!/bin/sh\nprintf '%s\\n' phantom\nexit 1\n", encoding="utf-8"
        )
        stub.chmod(0o755)
        environment = self.environment(extra={
            "PATH": f"{stub_directory}:{os.environ.get('PATH', '')}"
        })

        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        bash_script = self.sandbox / "failed-list.bash"
        bash_script.write_text(
            self.run_cli("completions", "bash").stdout, encoding="utf-8"
        )
        bash_probe = r'''source "$1"
COMP_WORDS=(skillset use p); COMP_CWORD=2; _skillset_completion
printf '%s\n' "${#COMPREPLY[@]}"'''
        bash_result = subprocess.run(
            [bash, "-c", bash_probe, "bash", str(bash_script)],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(bash_result.returncode, 0, bash_result.stderr)
        self.assertEqual(bash_result.stdout, "0\n")

        zsh_script = self.run_cli("completions", "zsh").stdout
        self.assertIn(
            'output="$(command skillset list 2>/dev/null)" || return 0',
            zsh_script,
        )

        fish = shutil.which("fish")
        if fish is not None:
            fish_script = self.sandbox / "failed-list.fish"
            fish_script.write_text(
                self.run_cli("completions", "fish").stdout, encoding="utf-8"
            )
            fish_result = subprocess.run(
                [
                    fish, "-c", "source $argv[1]; complete -C 'skillset use p'",
                    str(fish_script),
                ],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(fish_result.returncode, 0, fish_result.stderr)
            self.assertEqual(fish_result.stdout, "")

    def test_generated_completion_scripts_pass_available_shell_syntax_checks(self):
        checked = []
        for shell in ("bash", "zsh", "fish"):
            executable = shutil.which(shell)
            if executable is None:
                continue
            with self.subTest(shell=shell):
                generated = self.run_cli("completions", shell)
                checked.append(shell)
                self.assertEqual(generated.returncode, 0, generated.stderr)
                parsed = subprocess.run(
                    [executable, "-n"],
                    input=generated.stdout,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(parsed.returncode, 0, parsed.stderr)
        self.assertIn("bash", checked)

    def test_generated_zsh_completion_script_passes_syntax_check(self):
        zsh = shutil.which("zsh")
        if zsh is None:
            self.skipTest("zsh is not installed")

        generated = self.run_cli("completions", "zsh")

        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual(generated.stderr, "")
        parsed = subprocess.run(
            [zsh, "-n"],
            input=generated.stdout,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)

    def test_generated_zsh_completion_runs_on_first_autoload_call(self):
        zsh = shutil.which("zsh")
        if zsh is None:
            self.skipTest("zsh is not installed")
        generated = self.run_cli("completions", "zsh")
        completion_directory = self.sandbox / "zsh-completions"
        completion_directory.mkdir()
        (completion_directory / "_skillset").write_text(
            generated.stdout, encoding="utf-8"
        )
        probe = r'''fpath=("$1" $fpath)
autoload -Uz compinit
compinit -D
_arguments() { print -r -- first-autoload-call; return 0; }
_skillset'''

        result = subprocess.run(
            [zsh, "-f", "-c", probe, "zsh", str(completion_directory)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "first-autoload-call\n")

    def test_doctor_accepts_healthy_state_without_mutation_or_findings(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        self.write_skill(skills, "alpha", """
            name: alpha
            description: healthy metadata
        """)
        self.write_lock(
            self.root / "skillsets" / "default" / ".skill-lock.json",
            {"version": 3, "skills": {"alpha": {}}, "dismissed": {}},
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assert_no_doctor_findings(result)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_fix_creates_a_missing_empty_skillset_lockfile_after_confirmation(self):
        self.initialize()
        lockfile = self.root / "skillsets" / "default" / ".skill-lock.json"
        lockfile.unlink()

        result = self.run_cli("doctor", "--fix", input_text="yes\n")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertIn("Create these safe replacement files?", result.stderr)
        self.assertIn(str(lockfile), result.stderr)
        self.assertIn(f"skillset: repaired: created {lockfile}", result.stderr)
        self.assertEqual(json.loads(lockfile.read_text(encoding="utf-8")), EMPTY_LOCK)
        diagnosed = self.run_cli("doctor")
        self.assertEqual(diagnosed.returncode, 0, diagnosed.stderr)
        self.assert_no_doctor_findings(diagnosed)

    def test_doctor_fix_does_not_mutate_when_confirmation_is_declined(self):
        self.initialize()
        lockfile = self.root / "skillsets" / "default" / ".skill-lock.json"
        lockfile.unlink()
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor", "--fix", input_text="no\n")

        self.assert_refused(result)
        self.assertIn("Proceed? [y/N]", result.stderr)
        self.assertIn("lockfile is missing", result.stderr)
        self.assertFalse(lockfile.exists())
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_fix_never_invents_lock_metadata_for_nonempty_skills(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        self.write_skill(skills, "existing", """
            name: existing
            description: retained without guessed lock metadata
        """)
        lockfile = self.root / "skillsets" / "default" / ".skill-lock.json"
        lockfile.unlink()

        result = self.run_cli("doctor", "--fix", input_text="yes\n")

        self.assert_refused(result)
        self.assertNotIn("Create these safe replacement files?", result.stderr)
        self.assertIn("lockfile is missing", result.stderr)
        self.assertFalse(lockfile.exists())

    def test_doctor_fix_recreates_a_missing_advisory_lock_after_confirmation(self):
        self.initialize()
        advisory_lock = self.root / ".skillset.lock"
        advisory_lock.unlink()

        result = self.run_cli("doctor", "--fix", input_text="y\n")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertIn(str(advisory_lock), result.stderr)
        self.assertIn(f"skillset: repaired: created {advisory_lock}", result.stderr)
        self.assertTrue(advisory_lock.is_file())

    def test_doctor_aggregates_pristine_home_without_creating_agents_root(self):
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        self.assertEqual(result.stdout, "")
        self.assert_uninitialized_doctor_findings(result, self.root)
        self.assertEqual(self.doctor_findings(result, "warning"), [])
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_aggregates_existing_root_with_missing_advisory_lock(self):
        self.root.mkdir()
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        self.assertEqual(result.stdout, "")
        self.assert_uninitialized_doctor_findings(result, self.root)
        self.assertEqual(self.doctor_findings(result, "warning"), [])
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_refuses_non_directory_managed_roots_without_child_access(self):
        for index, kind in enumerate(("symlink", "regular-file")):
            with self.subTest(kind=kind):
                home = self.new_home(f"doctor-managed-root-{index}")
                root = home / ".agents"
                external_root = None
                if kind == "symlink":
                    external_home = self.new_home("doctor-external-layout")
                    external_root = self.make_managed_layout(external_home)
                    (external_root / ".skillset.lock").write_text("", encoding="utf-8")
                    self.write_skill(
                        external_root / "skillsets" / "default" / "skills",
                        "external-sentinel",
                        "name: external-sentinel\n"
                        "description: metadata beyond the managed-root boundary",
                    )
                    self.write_lock(
                        external_root / "skillsets" / "default" / ".skill-lock.json",
                        {
                            "version": 3,
                            "skills": {"external-sentinel": {}},
                            "dismissed": {},
                        },
                    )
                    root.symlink_to(external_root, target_is_directory=True)
                else:
                    root.write_bytes(b"not a managed directory\n")

                followed = self.sandbox / f"doctor-managed-root-followed-{index}"
                child_prefix = str(root) + os.sep
                fault = self.fault_environment(
                    f"""
                    import os
                    from pathlib import Path
                    marker = Path({str(followed)!r})
                    child_prefix = {child_prefix!r}
                    original_lstat = os.lstat
                    def guarded_lstat(path, *args, **kwargs):
                        candidate = os.fspath(path)
                        if isinstance(candidate, str) and candidate.startswith(child_prefix):
                            marker.write_text(candidate, encoding="utf-8")
                        return original_lstat(path, *args, **kwargs)
                    os.lstat = guarded_lstat
                    """
                )
                home_before = self.filesystem_snapshot(home)
                external_before = (
                    self.filesystem_snapshot(external_root)
                    if external_root is not None
                    else None
                )

                result = self.run_cli(
                    "doctor", home=home, extra_environment=fault
                )

                self.assert_refused(result)
                self.assertEqual(result.stdout, "")
                errors = self.doctor_findings(result, "error")
                self.assertEqual(len(errors), 1, errors)
                finding = errors[0].lower()
                self.assertIn(str(root).lower(), finding)
                self.assertIn("managed root", finding)
                self.assertIn("real directory", finding)
                self.assertEqual(self.doctor_findings(result, "warning"), [])
                self.assertNotIn("healthy", result.stderr.lower())
                self.assertNotIn("external-sentinel", result.stderr)
                self.assertNotIn("metadata beyond", result.stderr)
                self.assertFalse(followed.exists(), "doctor inspected a managed-root child")
                self.assertEqual(self.filesystem_snapshot(home), home_before)
                if external_root is not None:
                    self.assertEqual(
                        self.filesystem_snapshot(external_root), external_before
                    )

    def test_doctor_rejects_symlinked_skillsets_before_descendant_access(self):
        external_skillsets = self.sandbox / "external-skillsets"
        default = external_skillsets / "default"
        (default / "skills").mkdir(parents=True)
        self.write_skill(
            default / "skills",
            "external-sentinel",
            "name: external-sentinel\n"
            "description: metadata beyond the skillsets container boundary",
        )
        self.write_lock(
            default / ".skill-lock.json",
            {
                "version": 3,
                "skills": {"external-sentinel": {}},
                "dismissed": {},
            },
        )

        self.root.mkdir()
        (self.root / ".skillset.lock").write_text("", encoding="utf-8")
        skillsets = self.root / "skillsets"
        skillsets.symlink_to(external_skillsets, target_is_directory=True)
        (self.root / "active").symlink_to("skillsets/default")
        (self.root / "skills").symlink_to("active/skills")
        (self.root / ".skill-lock.json").symlink_to("active/.skill-lock.json")

        descendant_accessed = self.sandbox / "doctor-skillsets-descendant-accessed"
        descendant_prefix = str(skillsets) + os.sep
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            marker = Path({str(descendant_accessed)!r})
            descendant_prefix = {descendant_prefix!r}
            original_lstat = os.lstat
            original_iterdir = Path.iterdir
            def guarded_lstat(path, *args, **kwargs):
                candidate = os.fsdecode(os.fspath(path))
                if candidate.startswith(descendant_prefix):
                    marker.write_text(candidate, encoding="utf-8")
                return original_lstat(path, *args, **kwargs)
            def guarded_iterdir(path, *args, **kwargs):
                candidate = os.fsdecode(os.fspath(path))
                if candidate == descendant_prefix.rstrip(os.sep):
                    marker.write_text(candidate, encoding="utf-8")
                return original_iterdir(path, *args, **kwargs)
            os.lstat = guarded_lstat
            Path.iterdir = guarded_iterdir
            """
        )
        home_before = self.filesystem_snapshot(self.home)
        external_before = self.filesystem_snapshot(external_skillsets)

        result = self.run_cli("doctor", extra_environment=fault)

        self.assert_refused(result)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            self.doctor_findings(result, "error"),
            [f"skillset: error: skillsets directory symlink is not allowed: {skillsets}"],
        )
        self.assertEqual(self.doctor_findings(result, "warning"), [])
        self.assertNotIn("external-sentinel", result.stdout + result.stderr)
        self.assertNotIn("metadata beyond", result.stdout + result.stderr)
        self.assertFalse(
            descendant_accessed.exists(),
            "doctor inspected a descendant beneath the symlinked skillsets container",
        )
        self.assertEqual(self.filesystem_snapshot(self.home), home_before)
        self.assertEqual(
            self.filesystem_snapshot(external_skillsets), external_before
        )

    def test_doctor_rejects_mismatched_configured_link_before_descendant_access(self):
        configured = self.sandbox / "configured-doctor-source"
        configured.mkdir()
        mismatched = self.sandbox / "mismatched-doctor-source"
        default = mismatched / "default"
        (default / "skills").mkdir(parents=True)
        self.write_skill(
            default / "skills",
            "external-sentinel",
            "name: external-sentinel\n"
            "description: metadata beyond a mismatched configured link",
        )
        self.write_lock(default / ".skill-lock.json")
        self.write_config(self.home, configured)
        (self.root / ".skillset.lock").write_text("", encoding="utf-8")
        skillsets = self.root / "skillsets"
        skillsets.symlink_to(mismatched, target_is_directory=True)
        (self.root / "active").symlink_to("skillsets/default")
        (self.root / "skills").symlink_to("active/skills")
        (self.root / ".skill-lock.json").symlink_to("active/.skill-lock.json")

        descendant_accessed = self.sandbox / "configured-link-descendant-accessed"
        descendant_prefix = str(skillsets) + os.sep
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            marker = Path({str(descendant_accessed)!r})
            descendant_prefix = {descendant_prefix!r}
            original_lstat = os.lstat
            original_iterdir = Path.iterdir
            def guarded_lstat(path, *args, **kwargs):
                candidate = os.fsdecode(os.fspath(path))
                if candidate.startswith(descendant_prefix):
                    marker.write_text(candidate, encoding="utf-8")
                return original_lstat(path, *args, **kwargs)
            def guarded_iterdir(path, *args, **kwargs):
                candidate = os.fsdecode(os.fspath(path))
                if candidate == descendant_prefix.rstrip(os.sep):
                    marker.write_text(candidate, encoding="utf-8")
                return original_iterdir(path, *args, **kwargs)
            os.lstat = guarded_lstat
            Path.iterdir = guarded_iterdir
            """
        )
        home_before = self.filesystem_snapshot(self.home)
        configured_before = self.filesystem_snapshot(configured)
        mismatched_before = self.filesystem_snapshot(mismatched)

        result = self.run_cli("doctor", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn(
            "configured skillsets link is noncanonical", result.stdout + result.stderr
        )
        self.assertNotIn("external-sentinel", result.stdout + result.stderr)
        self.assertNotIn("metadata beyond", result.stdout + result.stderr)
        self.assertFalse(descendant_accessed.exists())
        self.assertEqual(self.filesystem_snapshot(self.home), home_before)
        self.assertEqual(self.filesystem_snapshot(configured), configured_before)
        self.assertEqual(self.filesystem_snapshot(mismatched), mismatched_before)

    def test_doctor_rejects_structurally_invalid_configured_links_without_source_access(
        self,
    ):
        external = self.sandbox / "configured-link-structure-source"
        default = external / "default"
        (default / "skills").mkdir(parents=True)
        self.write_lock(default / ".skill-lock.json")
        source_prefix = str(external) + os.sep
        cases = (
            ("missing", None, "configured skillsets link is missing"),
            ("directory", "directory", "configured skillsets link must be a symlink"),
            ("file", "file", "configured skillsets link must be a symlink"),
        )

        for index, (label, entry_kind, expected) in enumerate(cases):
            with self.subTest(label=label):
                home = self.new_home(f"configured-link-structure-{index}")
                root = home / ".agents"
                self.write_config(home, external)
                (root / ".skillset.lock").write_text("", encoding="utf-8")
                skillsets = root / "skillsets"
                if entry_kind == "directory":
                    skillsets.mkdir()
                elif entry_kind == "file":
                    skillsets.write_text("not a link\n", encoding="utf-8")
                (root / "active").symlink_to("skillsets/default")
                (root / "skills").symlink_to("active/skills")
                (root / ".skill-lock.json").symlink_to("active/.skill-lock.json")

                descendant_accessed = (
                    self.sandbox / f"configured-structure-descendant-{index}"
                )
                fault = self.fault_environment(
                    f"""
                    import os
                    from pathlib import Path
                    marker = Path({str(descendant_accessed)!r})
                    source = {str(external)!r}
                    source_prefix = {source_prefix!r}
                    original_lstat = os.lstat
                    original_iterdir = Path.iterdir
                    def guarded_lstat(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate.startswith(source_prefix):
                            marker.write_text(candidate, encoding="utf-8")
                        return original_lstat(path, *args, **kwargs)
                    def guarded_iterdir(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate == source:
                            marker.write_text(candidate, encoding="utf-8")
                        return original_iterdir(path, *args, **kwargs)
                    os.lstat = guarded_lstat
                    Path.iterdir = guarded_iterdir
                    """
                )
                home_before = self.filesystem_snapshot(home)
                external_before = self.filesystem_snapshot(external)

                result = self.run_cli(
                    "doctor", home=home, extra_environment=fault
                )

                self.assert_refused(result)
                errors = self.doctor_findings(result, "error")
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(expected, errors[0])
                self.assertEqual(self.doctor_findings(result, "warning"), [])
                self.assertFalse(
                    descendant_accessed.exists(),
                    "doctor inspected the configured source after link rejection",
                )
                self.assertEqual(self.filesystem_snapshot(home), home_before)
                self.assertEqual(
                    self.filesystem_snapshot(external), external_before
                )

    def test_doctor_reports_configured_link_permission_failures_without_source_access(
        self,
    ):
        external = self.sandbox / "configured-link-permission-source"
        default = external / "default"
        (default / "skills").mkdir(parents=True)
        self.write_lock(default / ".skill-lock.json")
        source_prefix = str(external) + os.sep
        cases = (
            ("lstat", "could not inspect skillsets directory"),
            ("readlink", "could not read configured skillsets link"),
        )

        for index, (failure, expected) in enumerate(cases):
            with self.subTest(failure=failure):
                home = self.new_home(f"configured-link-permission-{index}")
                root = home / ".agents"
                self.write_config(home, external)
                (root / ".skillset.lock").write_text("", encoding="utf-8")
                skillsets = root / "skillsets"
                skillsets.symlink_to(external, target_is_directory=True)
                (root / "active").symlink_to("skillsets/default")
                (root / "skills").symlink_to("active/skills")
                (root / ".skill-lock.json").symlink_to("active/.skill-lock.json")

                descendant_accessed = (
                    self.sandbox / f"configured-permission-descendant-{index}"
                )
                fault = self.fault_environment(
                    f"""
                    import errno
                    import os
                    from pathlib import Path
                    failure = {failure!r}
                    marker = Path({str(descendant_accessed)!r})
                    link = {str(skillsets)!r}
                    source = {str(external)!r}
                    source_prefix = {source_prefix!r}
                    original_lstat = os.lstat
                    original_readlink = os.readlink
                    original_path_lstat = Path.lstat
                    original_iterdir = Path.iterdir
                    def guarded_lstat(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate == link and failure == "lstat":
                            raise PermissionError(
                                errno.EACCES, os.strerror(errno.EACCES), candidate
                            )
                        if candidate.startswith(source_prefix):
                            marker.write_text(candidate, encoding="utf-8")
                        return original_lstat(path, *args, **kwargs)
                    def guarded_path_lstat(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate == link and failure == "lstat":
                            raise PermissionError(
                                errno.EACCES, os.strerror(errno.EACCES), candidate
                            )
                        if candidate.startswith(source_prefix):
                            marker.write_text(candidate, encoding="utf-8")
                        return original_path_lstat(path, *args, **kwargs)
                    def guarded_readlink(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate == link and failure == "readlink":
                            raise PermissionError(
                                errno.EACCES, os.strerror(errno.EACCES), candidate
                            )
                        return original_readlink(path, *args, **kwargs)
                    def guarded_iterdir(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate == source:
                            marker.write_text(candidate, encoding="utf-8")
                        return original_iterdir(path, *args, **kwargs)
                    os.lstat = guarded_lstat
                    os.readlink = guarded_readlink
                    Path.lstat = guarded_path_lstat
                    Path.iterdir = guarded_iterdir
                    """
                )
                home_before = self.filesystem_snapshot(home)
                external_before = self.filesystem_snapshot(external)

                result = self.run_cli(
                    "doctor", home=home, extra_environment=fault
                )

                self.assert_refused(result)
                errors = self.doctor_findings(result, "error")
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(expected, errors[0])
                self.assertIn("Permission denied", errors[0])
                self.assertEqual(self.doctor_findings(result, "warning"), [])
                self.assertFalse(
                    descendant_accessed.exists(),
                    "doctor inspected the configured source after permission failure",
                )
                self.assertEqual(self.filesystem_snapshot(home), home_before)
                self.assertEqual(
                    self.filesystem_snapshot(external), external_before
                )

    def test_doctor_rejects_invalid_config_before_skillsets_descendant_access(self):
        external = self.sandbox / "invalid-config-doctor-source"
        default = external / "default"
        (default / "skills").mkdir(parents=True)
        self.write_skill(
            default / "skills",
            "external-sentinel",
            "name: external-sentinel\n"
            "description: metadata beyond an invalid configuration",
        )
        self.write_lock(default / ".skill-lock.json")
        cases = (
            ("malformed", "{not json\n", "invalid config"),
            (
                "wrong-version",
                json.dumps(
                    {"version": 2, "skillsets_directory": str(external)}
                )
                + "\n",
                "integer version 1",
            ),
        )

        for index, (label, raw_config, expected) in enumerate(cases):
            with self.subTest(label=label):
                home = self.new_home(f"invalid-doctor-config-{index}")
                root = home / ".agents"
                self.write_config(home, external, raw=raw_config)
                (root / ".skillset.lock").write_text("", encoding="utf-8")
                skillsets = root / "skillsets"
                skillsets.symlink_to(external, target_is_directory=True)
                (root / "active").symlink_to("skillsets/default")
                (root / "skills").symlink_to("active/skills")
                (root / ".skill-lock.json").symlink_to("active/.skill-lock.json")

                descendant_accessed = (
                    self.sandbox / f"invalid-config-descendant-accessed-{index}"
                )
                descendant_prefix = str(skillsets) + os.sep
                fault = self.fault_environment(
                    f"""
                    import os
                    from pathlib import Path
                    marker = Path({str(descendant_accessed)!r})
                    descendant_prefix = {descendant_prefix!r}
                    original_lstat = os.lstat
                    original_iterdir = Path.iterdir
                    def guarded_lstat(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate.startswith(descendant_prefix):
                            marker.write_text(candidate, encoding="utf-8")
                        return original_lstat(path, *args, **kwargs)
                    def guarded_iterdir(path, *args, **kwargs):
                        candidate = os.fsdecode(os.fspath(path))
                        if candidate == descendant_prefix.rstrip(os.sep):
                            marker.write_text(candidate, encoding="utf-8")
                        return original_iterdir(path, *args, **kwargs)
                    os.lstat = guarded_lstat
                    Path.iterdir = guarded_iterdir
                    """
                )
                home_before = self.filesystem_snapshot(home)
                external_before = self.filesystem_snapshot(external)

                result = self.run_cli(
                    "doctor", home=home, extra_environment=fault
                )

                self.assert_refused(result)
                errors = self.doctor_findings(result, "error")
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(expected, errors[0])
                self.assertNotIn(
                    "external-sentinel", result.stdout + result.stderr
                )
                self.assertNotIn("metadata beyond", result.stdout + result.stderr)
                self.assertFalse(
                    descendant_accessed.exists(),
                    "doctor inspected a descendant with invalid configuration",
                )
                self.assertEqual(self.filesystem_snapshot(home), home_before)
                self.assertEqual(
                    self.filesystem_snapshot(external), external_before
                )

    def test_doctor_aggregates_uninitialized_state_without_creating_files(self):
        self.root.mkdir()
        (self.root / ".skillset.lock").write_text("", encoding="utf-8")
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        errors = "\n".join(self.doctor_findings(result, "error")).lower()
        for component in ("skillsets", "active", "skills", ".skill-lock.json"):
            with self.subTest(component=component):
                self.assertIn(component, errors)
        self.assertGreaterEqual(len(self.doctor_findings(result, "error")), 4)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_aggregates_partial_and_structurally_invalid_state(self):
        self.root.mkdir()
        (self.root / ".skillset.lock").write_text("", encoding="utf-8")
        skillsets = self.root / "skillsets"
        skillsets.mkdir()
        (self.root / "active").write_text("not an alias\n", encoding="utf-8")
        (self.root / "skills").symlink_to("skillsets/default/skills")
        (self.root / ".skillset-use.staging").write_text(
            "stale use state\n", encoding="utf-8"
        )
        (skillsets / ".skillset-create-orphan.staging").mkdir()

        default = skillsets / "default"
        default.mkdir()
        self.write_lock(default / ".skill-lock.json", raw="{malformed\n")
        self.make_set(
            self.root,
            "wrongversion",
            {"version": 2, "skills": {}, "dismissed": {}},
        )
        self.make_set(self.root, "Bad Name")
        external = self.home / "external-set"
        (external / "skills").mkdir(parents=True)
        self.write_lock(external / ".skill-lock.json")
        (skillsets / "linked").symlink_to(external, target_is_directory=True)
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        error_lines = self.doctor_findings(result, "error")
        expected_findings = (
            (default / "skills", "missing"),
            (default / ".skill-lock.json", "invalid"),
            (skillsets / "wrongversion" / ".skill-lock.json", "version"),
            (skillsets / "Bad Name", "invalid", "name"),
            (skillsets / "linked", "symlink"),
            (self.root / ".skillset-use.staging", "stale"),
            (skillsets / ".skillset-create-orphan.staging", "stale"),
            (self.root / "active", "symlink"),
            (self.root / "skills", "alias", "canonical"),
            (self.root / ".skill-lock.json", "alias", "missing"),
        )
        for fragments in expected_findings:
            with self.subTest(finding=fragments):
                self.assert_finding_line(error_lines, *fragments)
        self.assertGreaterEqual(len(error_lines), len(expected_findings))
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_reports_nonregular_advisory_locks_and_continues_diagnosis(self):
        cases = (
            ("symlink", "symlink"),
            ("directory", "regular"),
        )
        for index, (kind, reason) in enumerate(cases):
            with self.subTest(kind=kind):
                home = self.new_home(f"doctor-nonregular-lock-{index}")
                root = home / ".agents"
                root.mkdir()
                lock_path = root / ".skillset.lock"
                fault = None
                followed = None
                if kind == "symlink":
                    external = home / "external-lock"
                    external.write_bytes(b"must not be opened through the link")
                    lock_path.symlink_to("../external-lock")
                    followed = self.sandbox / "doctor-followed-lock-symlink"
                    identity = (external.stat().st_dev, external.stat().st_ino)
                    fault = self.fault_environment(
                        f"""
                        import fcntl
                        import os
                        from pathlib import Path
                        marker = Path({str(followed)!r})
                        external_identity = {identity!r}
                        original_flock = fcntl.flock
                        def guarded_flock(file, operation):
                            descriptor = file if isinstance(file, int) else file.fileno()
                            metadata = os.fstat(descriptor)
                            if (metadata.st_dev, metadata.st_ino) == external_identity:
                                marker.write_text("followed", encoding="utf-8")
                            return original_flock(file, operation)
                        fcntl.flock = guarded_flock
                        """
                    )
                else:
                    lock_path.mkdir()
                before = self.filesystem_snapshot(home)

                result = self.run_cli(
                    "doctor", home=home, extra_environment=fault
                )

                self.assert_refused(result)
                errors = self.doctor_findings(result, "error")
                self.assert_finding_line(errors, lock_path, "lock", reason)
                for path, category in (
                    (root / "skills", "alias"),
                    (root / ".skill-lock.json", "alias"),
                    (root / "active", "active"),
                    (root / "skillsets", "skillsets"),
                ):
                    self.assert_finding_line(errors, path, category, "missing")
                if followed is not None:
                    self.assertFalse(followed.exists(), "doctor followed lock symlink")
                self.assertEqual(self.filesystem_snapshot(home), before)

    def test_doctor_diagnoses_noncanonical_aliases_and_active_targets(self):
        def relink(path, target):
            path.unlink()
            path.symlink_to(target)

        cases = (
            (
                "skills-alias",
                ("skills", "alias"),
                lambda root: relink(root / "skills", "skillsets/default/skills"),
            ),
            (
                "lock-alias",
                (".skill-lock.json", "alias"),
                lambda root: relink(
                    root / ".skill-lock.json",
                    "skillsets/default/.skill-lock.json",
                ),
            ),
            (
                "absolute-active",
                ("active", "canonical"),
                lambda root: relink(
                    root / "active", str(root / "skillsets" / "default")
                ),
            ),
            (
                "missing-active-target",
                ("active", "missing"),
                lambda root: relink(root / "active", "skillsets/missing"),
            ),
        )
        for index, (label, keywords, mutate) in enumerate(cases):
            with self.subTest(layout=label):
                home = self.new_home(f"doctor-alias-{index}")
                root = self.make_managed_layout(home)
                (root / ".skillset.lock").write_text("", encoding="utf-8")
                mutate(root)
                before = self.filesystem_snapshot(home)

                result = self.run_cli("doctor", home=home)

                self.assert_refused(result)
                errors = "\n".join(
                    self.doctor_findings(result, "error")
                ).lower()
                for keyword in keywords:
                    self.assertIn(keyword, errors)
                self.assertEqual(self.filesystem_snapshot(home), before)

    def test_doctor_reports_all_invalid_skill_metadata_as_errors(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        invalid_utf = skills / "invalid-utf"
        invalid_utf.mkdir()
        invalid_utf.joinpath("SKILL.md").write_bytes(
            b"---\nname: invalid-utf\ndescription: \xff\n---\n"
        )
        malformed = skills / "malformed-frontmatter"
        malformed.mkdir()
        malformed.joinpath("SKILL.md").write_text(
            "---\nname: malformed\ndescription: no closing delimiter\n",
            encoding="utf-8",
        )
        (skills / "missing-skill-file").mkdir()
        self.write_skill(skills, "valid-sibling", """
            name: valid-sibling
            description: valid metadata does not hide sibling errors
        """)
        self.write_lock(
            self.root / "skillsets" / "default" / ".skill-lock.json",
            {
                "version": 3,
                "skills": {
                    "invalid-utf": {},
                    "malformed-frontmatter": {},
                    "missing-skill-file": {},
                    "valid-sibling": {},
                },
                "dismissed": {},
            },
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        errors = self.doctor_findings(result, "error")
        expected = {
            "invalid-utf": "utf",
            "malformed-frontmatter": "frontmatter",
            "missing-skill-file": "skill.md",
        }
        for directory, reason in expected.items():
            with self.subTest(directory=directory):
                self.assert_finding_line(errors, directory, reason)
        self.assertEqual(self.doctor_findings(result, "warning"), [])
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_lock_content_mismatches_are_warning_only_in_both_directions(self):
        self.initialize()
        skillset = self.root / "skillsets" / "default"
        self.write_skill(skillset / "skills", "directory-only", """
            name: directory-only
            description: installed without lock metadata
        """)
        self.write_lock(
            skillset / ".skill-lock.json",
            {"version": 3, "skills": {"lock-only": {}}, "dismissed": {}},
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.doctor_findings(result, "error"), [])
        warnings = self.doctor_findings(result, "warning")
        self.assertEqual(len(warnings), 2, warnings)
        self.assert_finding_line(
            warnings, "directory-only", "installed", "missing", "lockfile"
        )
        self.assert_finding_line(
            warnings, "lock-only", "lockfile", "no real", "directory"
        )
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_escapes_terminal_controls_on_one_physical_line_per_finding(self):
        self.initialize()
        unsafe_name = "bad\x1b\u2028\u2029name"
        self.make_set(self.root, unsafe_name)
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        self.assertEqual(result.stdout, "")
        for raw in ("\x1b", "\u2028", "\u2029"):
            self.assertNotIn(raw, result.stderr)
        self.assertIn(r"bad\x1b\u2028\u2029name", result.stderr)
        errors = self.doctor_findings(result, "error")
        self.assertEqual(len(errors), 1, errors)
        self.assertEqual(result.stderr.splitlines(), errors)
        self.assertEqual(self.doctor_findings(result, "warning"), [])
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_ignores_regular_skill_entries_and_never_follows_skill_symlinks(self):
        self.initialize()
        skillset = self.root / "skillsets" / "default"
        skills = skillset / "skills"
        (skills / "ordinary-file").write_text("not a directory\n", encoding="utf-8")
        external = self.home / "external-skill"
        external.mkdir()
        external.joinpath("SKILL.md").write_text(
            "---\nname: external-secret\ndescription: must not be read\n---\n",
            encoding="utf-8",
        )
        (skills / "linked-directory").symlink_to(
            external, target_is_directory=True
        )
        linked_file = skills / "linked-skill-file"
        linked_file.mkdir()
        linked_file.joinpath("SKILL.md").symlink_to(external / "SKILL.md")
        self.write_lock(
            skillset / ".skill-lock.json",
            {
                "version": 3,
                "skills": {
                    "ordinary-file": {},
                    "linked-directory": {},
                    "linked-skill-file": {},
                },
                "dismissed": {},
            },
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("doctor")

        self.assert_refused(result)
        errors = "\n".join(self.doctor_findings(result, "error")).lower()
        self.assertIn("linked-directory", errors)
        self.assertIn("linked-skill-file", errors)
        self.assertIn("symlink", errors)
        warnings = "\n".join(self.doctor_findings(result, "warning")).lower()
        self.assertIn("ordinary-file", warnings)
        self.assertNotIn("external-secret", result.stdout + result.stderr)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_doctor_waits_for_advisory_lock_without_blind_sleep(self):
        self.initialize()
        attempted = self.sandbox / "doctor-lock-attempted"
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
        with (self.root / ".skillset.lock").open("a+") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            process = self.popen_cli("doctor", extra_environment=fault)
            try:
                self.wait_for_path(attempted, process)
                self.assertIsNone(process.poll(), "doctor did not block on the lock")
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
        try:
            stdout, stderr = process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)
        self.assertEqual(process.returncode, 0, (stdout, stderr))
        self.assert_no_doctor_findings(
            subprocess.CompletedProcess([], process.returncode, stdout, stderr)
        )

    def test_pristine_home_doctor_locks_home_directory_before_diagnosis(self):
        attempted = self.sandbox / "pristine-doctor-lock-attempted"
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
        before = self.filesystem_snapshot(self.home)
        home_fd = os.open(self.home, os.O_RDONLY | os.O_DIRECTORY)
        process = None
        try:
            fcntl.flock(home_fd, fcntl.LOCK_EX)
            process = self.popen_cli("doctor", extra_environment=fault)
            self.wait_for_path(attempted, process)
            self.assertIsNone(process.poll(), "doctor did not block on HOME")
            fcntl.flock(home_fd, fcntl.LOCK_UN)
            stdout, stderr = process.communicate(timeout=5)
        finally:
            fcntl.flock(home_fd, fcntl.LOCK_UN)
            os.close(home_fd)
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=2)

        result = subprocess.CompletedProcess([], process.returncode, stdout, stderr)
        self.assert_refused(result)
        self.assert_uninitialized_doctor_findings(result, self.root)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_noninitializing_commands_share_invalid_layout_fail_fast_boundary(self):
        self.initialize()
        self.make_set(self.root, "victim")
        staging = self.root / ".skillset-use.staging"
        staging.write_text("common invalid state\n", encoding="utf-8")
        environment, record = self.fake_npx_environment()
        before = self.filesystem_snapshot(self.home)
        commands = (
            ("create", "new"),
            ("use", "default"),
            ("rename", "victim", "renamed"),
            ("remove", "victim", "--yes"),
            ("list",),
            ("codex", "list"),
            ("current",),
            ("show", "default"),
            ("skills", "list"),
        )

        for arguments in commands:
            with self.subTest(command=arguments[0]):
                result = self.run_cli(
                    *arguments, extra_environment=environment, input_text="yes\n"
                )
                self.assert_refused(result)
                self.assertIn(str(staging), result.stdout + result.stderr)
                self.assertNotIn("Remove skillset", result.stderr)
                self.assertEqual(self.filesystem_snapshot(self.home), before)
                self.assertFalse(record.exists(), f"{arguments[0]} invoked npx")

    def test_complete_command_workflow_and_managed_delegation(self):
        environment, record = self.fake_npx_environment()

        initialized = self.run_cli("init", "baseline")
        created = self.run_cli("create", "experiment")
        activated = self.run_cli("use", "experiment")
        listed = self.run_cli("list")
        current = self.run_cli("current")
        shown = self.run_cli("show", "experiment")
        renamed = self.run_cli("rename", "experiment", "trial")
        removed = self.run_cli("remove", "baseline", "--yes")
        delegated = self.run_cli(
            "skills", "list", "--json", extra_environment=environment
        )
        diagnosed = self.run_cli("doctor")

        for result in (
            initialized,
            created,
            activated,
            listed,
            current,
            shown,
            renamed,
            removed,
            delegated,
            diagnosed,
        ):
            self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(listed.stdout, "baseline\n* experiment\n")
        self.assertEqual(current.stdout, "experiment\n")
        self.assertEqual(shown.stdout, "No skills installed.\n")
        self.assert_aliases(self.root, "trial")
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "baseline"))
        self.assert_fake_argv(record, ["skills", "list", "--json", "--global"])
        self.assert_no_doctor_findings(diagnosed)

    def test_list_sorts_set_names_and_marks_only_the_active_set(self):
        self.initialize("middle")
        self.make_set(self.root, "zeta")
        self.make_set(self.root, "alpha")

        result = self.run_cli("list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "alpha\n* middle\nzeta\n")
        self.assertEqual(result.stderr, "")

    def test_codex_enable_disable_and_list_manage_only_canonical_links(self):
        self.initialize()
        self.make_set(self.root, "personal")
        codex_skills = self.home / ".codex" / "skills"
        codex_skills.mkdir(parents=True)
        (codex_skills / "unmanaged").mkdir()

        enabled = self.run_cli("codex", "enable", "personal")
        listed = self.run_cli("codex", "list")
        verbose = self.run_cli("codex", "list", "--verbose")

        link = codex_skills / "personal"
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(
            os.readlink(link), str(self.root / "skillsets" / "personal" / "skills")
        )
        self.assertEqual(listed.stdout, "[g] personal\n")
        self.assertEqual(
            verbose.stdout,
            "  SKILLSET     | SKILLS\n"
            "  -------------|------------\n"
            "  [g] personal | (no skills)\n",
        )

        enabled_active = self.run_cli("codex", "enable", "default")
        listed_active = self.run_cli("codex", "list")
        disabled = self.run_cli("codex", "disable", "personal")
        after_disable = self.run_cli("codex", "list")

        self.assertEqual(enabled_active.returncode, 0, enabled_active.stderr)
        self.assertEqual(listed_active.stdout, "[g] default\n[g] personal\n")
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertFalse(os.path.lexists(link))
        self.assertTrue((codex_skills / "unmanaged").is_dir())
        self.assertEqual(after_disable.stdout, "[g] default\n")

    def test_codex_operations_refuse_noncanonical_links_without_mutation(self):
        self.initialize()
        codex_skills = self.home / ".codex" / "skills"
        codex_skills.mkdir(parents=True)
        link = codex_skills / "default"
        link.symlink_to("/tmp/unmanaged-skills")
        before = self.filesystem_snapshot(self.home)

        for arguments in (("codex", "enable", "default"), ("codex", "disable", "default")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assert_refused(result)
                self.assertEqual(self.filesystem_snapshot(self.home), before)

        listed = self.run_cli("codex", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(listed.stdout, "")

    def test_codex_list_and_disable_accept_an_absolute_link_with_trailing_slash(self):
        self.initialize()
        codex_skills = self.home / ".codex" / "skills"
        codex_skills.mkdir(parents=True)
        link = codex_skills / "default"
        link.symlink_to(str(self.root / "skillsets" / "default" / "skills") + "/")

        listed = self.run_cli("codex", "list")
        disabled = self.run_cli("codex", "disable", "default")

        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(listed.stdout, "[g] default\n")
        self.assertEqual(disabled.returncode, 0, disabled.stderr)
        self.assertFalse(os.path.lexists(link))

    def test_codex_local_scope_is_independent_and_visibly_labeled(self):
        self.initialize()
        self.make_set(self.root, "personal")
        project = self.sandbox / "project"
        project.mkdir()

        global_enabled = self.run_cli("codex", "enable", "default")
        local_enabled = self.run_cli(
            "codex", "enable", "-l", "personal", cwd=project
        )
        global_list = self.run_cli("codex", "list", "-g")
        local_list = self.run_cli("codex", "list", "-l", cwd=project)
        combined_list = self.run_cli("codex", "list", cwd=project)
        local_verbose = self.run_cli(
            "codex", "list", "--local", "--verbose", cwd=project
        )

        self.assertEqual(global_enabled.returncode, 0, global_enabled.stderr)
        self.assertEqual(local_enabled.returncode, 0, local_enabled.stderr)
        self.assertTrue((self.home / ".codex" / "skills" / "default").is_symlink())
        self.assertTrue((project / ".codex" / "skills" / "personal").is_symlink())
        self.assertEqual(global_list.stdout, "default\n")
        self.assertEqual(local_list.stdout, "personal\n")
        self.assertEqual(combined_list.stdout, "[g] default\n[l] personal\n")
        self.assertEqual(
            local_verbose.stdout,
            "  SKILLSET | SKILLS\n"
            "  ---------|------------\n"
            "  personal | (no skills)\n",
        )
        local_disabled = self.run_cli(
            "codex", "disable", "personal", "-l", cwd=project
        )
        self.assertEqual(local_disabled.returncode, 0, local_disabled.stderr)
        self.assertFalse(os.path.lexists(project / ".codex" / "skills" / "personal"))
        self.assertTrue((self.home / ".codex" / "skills" / "default").is_symlink())

    def test_codex_combined_list_colorizes_scope_labels_only(self):
        self.initialize()
        self.make_set(self.root, "personal")
        project = self.sandbox / "project-colored"
        project.mkdir()
        self.assertEqual(self.run_cli("codex", "enable", "default").returncode, 0)
        self.assertEqual(
            self.run_cli("codex", "enable", "personal", "-l", cwd=project).returncode,
            0,
        )

        combined = self.run_cli_tty("codex", "list", cwd=project)
        global_only = self.run_cli_tty("codex", "list", "-g", cwd=project)

        self.assertEqual(combined.returncode, 0, combined.stderr)
        self.assertIn("\x1b[36m[g]\x1b[0m default", combined.stdout)
        self.assertIn("\x1b[32m[l]\x1b[0m personal", combined.stdout)
        self.assertEqual(global_only.returncode, 0, global_only.stderr)
        self.assertNotIn("[g]", global_only.stdout)

    def test_codex_enabled_skillsets_must_be_disabled_before_rename_or_remove(self):
        self.initialize()
        self.make_set(self.root, "personal")
        self.assertEqual(self.run_cli("codex", "enable", "personal").returncode, 0)
        before = self.filesystem_snapshot(self.home)

        renamed = self.run_cli("rename", "personal", "renamed")
        removed = self.run_cli("remove", "personal", "--yes")

        self.assert_refused(renamed)
        self.assert_refused(removed)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_verbose_list_prints_aligned_complete_inventory_for_both_flags(self):
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

        skills_cell = "alpha, malformed [invalid: missing description], zeta"
        expected = (
            "  SKILLSET | SKILLS\n"
            "  ---------|" + "-" * (len(skills_cell) + 1) + "\n"
            f"* default  | {skills_cell}\n"
            "  empty    | (no skills)\n"
        )
        for flag in ("-v", "--verbose"):
            with self.subTest(flag=flag):
                result = self.run_cli("list", flag)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)
                self.assertEqual(result.stderr, "")
                self.assertNotIn("\x1b", result.stdout)

    def test_verbose_list_colorizes_independent_segments_only_for_eligible_tty(self):
        self.initialize()
        self.make_set(self.root, "empty")
        skills = self.root / "skillsets/default/skills"
        self.write_skill(skills, "valid", "name: alpha\ndescription: valid")
        self.write_skill(skills, "warning", "name: warning")
        (skills / "error").mkdir()

        colored = self.run_cli_tty("list", "-v")

        self.assertEqual(colored.returncode, 0, colored.stderr)
        self.assertIn("\x1b[1mSKILLSET\x1b[0m", colored.stdout)
        self.assertIn("\x1b[2m|\x1b[0m", colored.stdout)
        self.assertRegex(colored.stdout, r"\x1b\[2m  -+\|-+\x1b\[0m")
        self.assertIn("\x1b[1m\x1b[36m*\x1b[0m ", colored.stdout)
        self.assertIn("\x1b[1m\x1b[36mdefault\x1b[0m", colored.stdout)
        self.assertIn("\x1b[36malpha\x1b[0m, error ", colored.stdout)
        self.assertIn("\x1b[31m[invalid: missing SKILL.md]\x1b[0m", colored.stdout)
        self.assertIn("\x1b[33m[invalid: missing description]\x1b[0m", colored.stdout)
        self.assertIn("\x1b[2m(no skills)\x1b[0m", colored.stdout)

        plain = self.run_cli("list", "-v")
        self.assertNotIn("\x1b", plain.stdout)

    def test_verbose_list_tty_escapes_controls_without_unapproved_sgr(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        controls = "\x1b\x7f\x9b\u202e\u2066"
        declared = f"valid{controls}name"
        directory = f"broken{controls}name"
        self.write_skill(skills, "valid", f"name: {declared}\ndescription: valid")
        (skills / directory).mkdir()

        result = self.run_cli_tty("list", "-v")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        escaped_declared = r"valid\x1b\x7f\x9b\u202e\u2066name"
        escaped_directory = r"broken\x1b\x7f\x9b\u202e\u2066name"
        self.assertIn(escaped_declared, result.stdout)
        self.assertIn(escaped_directory, result.stdout)
        self.assertIn(f"\x1b[36m{escaped_declared}\x1b[0m", result.stdout)
        self.assertIn(
            f"{escaped_directory} \x1b[31m[invalid: missing SKILL.md]\x1b[0m",
            result.stdout,
        )
        for raw in ("\x7f", "\x9b", "\u202e", "\u2066"):
            self.assertNotIn(raw, result.stdout)
        without_allowed_sgr = result.stdout
        for sgr in (
            "\x1b[0m",
            "\x1b[1m",
            "\x1b[2m",
            "\x1b[31m",
            "\x1b[33m",
            "\x1b[36m",
        ):
            without_allowed_sgr = without_allowed_sgr.replace(sgr, "")
        self.assertNotIn("\x1b", without_allowed_sgr)

    def test_verbose_list_tty_color_honors_environment_opt_outs(self):
        self.initialize()
        self.write_skill(
            self.root / "skillsets/default/skills",
            "valid",
            "name: alpha\ndescription: valid",
        )
        plain = self.run_cli("list", "-v").stdout
        for extra_environment in ({"NO_COLOR": "1"}, {"TERM": "dumb"}):
            with self.subTest(environment=extra_environment):
                result = self.run_cli_tty(
                    "list", "-v", extra_environment=extra_environment
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, plain)
                self.assertNotIn("\x1b", result.stdout)

    def test_verbose_list_caps_only_tty_separator_and_keeps_one_complete_data_line(self):
        self.initialize()
        declared = "a-very-long-skill-name-that-remains-complete"
        self.write_skill(
            self.root / "skillsets/default/skills",
            "valid",
            f"name: {declared}\ndescription: valid",
        )

        colored = self.run_cli_tty("list", "-v", terminal_columns=20)

        self.assertEqual(colored.returncode, 0, colored.stderr)
        self.assertEqual(
            colored.stdout.splitlines()[1],
            "\x1b[2m  ---------|--------\x1b[0m",
        )
        self.assertEqual(len(colored.stdout.splitlines()), 3)
        self.assertIn(declared, colored.stdout.splitlines()[2])

        captured = self.run_cli("list", "-v")
        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertEqual(
            captured.stdout.splitlines()[1],
            "  ---------|" + "-" * (len(declared) + 1),
        )

    def test_verbose_list_does_not_call_an_invalid_only_set_empty(self):
        self.initialize()
        broken = self.make_set(self.root, "broken-only")
        self.write_skill(broken / "skills", "malformed", "name: hidden")

        result = self.run_cli("list", "-v")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "  broken-only | malformed [invalid: missing description]\n",
            result.stdout,
        )
        self.assertNotIn("  broken-only | (no skills)\n", result.stdout)

    def test_verbose_list_measures_wide_and_combining_skill_names_by_display_cell(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        combining = "e\u0301" * 6
        self.write_skill(skills, "combining", f"name: {combining}\ndescription: valid")
        self.write_skill(skills, "wide", "name: 界界界\ndescription: valid")

        result = self.run_cli("list", "-v")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[1], "  ---------|" + "-" * 15)
        self.assertEqual(result.stdout.splitlines()[2], f"* default  | {combining}, 界界界")

    def test_verbose_list_visibly_escapes_declared_name_terminal_controls(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        declared = "jalapeño\x1b\x7f\u202eoutil"
        description = "résumé\x1b\x9b\u2066 text"
        self.write_skill(
            skills,
            "control-display",
            f"name: {declared}\ndescription: {description}",
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("list", "--verbose")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        for raw in ("\x1b", "\x7f", "\x9b", "\u202e", "\u2066"):
            self.assertNotIn(raw, result.stdout)
        displayed = r"jalapeño\x1b\x7f\u202eoutil"
        self.assertEqual(
            result.stdout,
            "  SKILLSET | SKILLS\n"
            "  ---------|" + "-" * (len(displayed) + 1) + "\n"
            f"* default  | {displayed}\n",
        )
        self.assertIn("jalapeño", result.stdout)
        self.assertNotIn("\t", result.stdout)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_verbose_list_visibly_escapes_invalid_directory_terminal_controls(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        directory = "broken\x1b\x7f\u202ename"
        (skills / directory).mkdir()

        result = self.run_cli("list", "--verbose")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        for raw in ("\x1b", "\x7f", "\u202e"):
            self.assertNotIn(raw, result.stdout)
        self.assertIn(
            r"broken\x1b\x7f\u202ename [invalid: missing SKILL.md]",
            result.stdout,
        )

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

    def test_current_escapes_unsafe_operational_errors_at_the_final_boundary(self):
        self.initialize()
        unsafe_target = "outside\x1b\u202e\u2028managed-root"
        (self.root / "active").unlink()
        (self.root / "active").symlink_to(unsafe_target)
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("current")

        self.assert_refused(result)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(result.stderr.endswith("\n"), result.stderr)
        self.assertTrue(lines[0].startswith("skillset: "), lines[0])
        for raw in ("\x1b", "\u202e", "\u2028"):
            self.assertNotIn(raw, result.stderr)
        for escaped in (r"\x1b", r"\u202e", r"\u2028"):
            self.assertIn(escaped, result.stderr)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_show_empty_set_prints_explanatory_message(self):
        self.initialize()

        result = self.run_cli("show")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "No skills installed.\n")
        self.assertEqual(result.stderr, "")

    def test_show_defaults_to_active_set_and_explicit_name_overrides_it(self):
        self.initialize("default")
        alternate = self.make_set(self.root, "alternate")
        self.write_skill(
            self.root / "skillsets/default/skills",
            "alpha",
            "name: alpha\ndescription: active",
        )
        self.write_skill(
            alternate / "skills", "beta", "name: beta\ndescription: explicit"
        )

        active = self.run_cli("show")
        explicit = self.run_cli("show", "alternate")
        switched = self.run_cli("use", "alternate")
        new_active = self.run_cli("show")

        self.assertIn("alpha", active.stdout)
        self.assertNotIn("beta", active.stdout)
        self.assertIn("beta", explicit.stdout)
        self.assertNotIn("alpha", explicit.stdout)
        self.assertEqual(switched.returncode, 0, switched.stderr)
        self.assertIn("beta", new_active.stdout)
        self.assertNotIn("alpha", new_active.stdout)

    def test_show_help_marks_name_as_optional(self):
        result = self.run_cli("show", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"usage: skillset show \[-h\] \[name\]")

    def test_show_prints_borderless_table_with_aligned_inner_delimiter(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        self.write_skill(skills, "short", "name: alpha\ndescription: Short")
        self.write_skill(
            skills, "long", "name: longer-name\ndescription: Longer description"
        )

        result = self.run_cli("show")

        self.assertEqual(
            result.stdout,
            "SKILL       | DESCRIPTION\n"
            "------------|-------------------\n"
            "alpha       | Short\n"
            "longer-name | Longer description\n",
        )
        self.assertNotIn("\x1b", result.stdout)

    def test_show_caps_only_tty_separator_to_terminal_width(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        description = "This complete description remains unchanged past the terminal width."
        self.write_skill(skills, "valid", f"name: alpha\ndescription: {description}")

        colored = self.run_cli_tty("show", terminal_columns=20)

        self.assertEqual(colored.returncode, 0, colored.stderr)
        colored_separator = colored.stdout.splitlines()[1]
        self.assertEqual(colored_separator, "\x1b[2m------|-------------\x1b[0m")
        self.assertIn(description, colored.stdout)

        for extra_environment in ({"NO_COLOR": "1"}, {"TERM": "dumb"}):
            with self.subTest(environment=extra_environment):
                plain_tty = self.run_cli_tty(
                    "show",
                    extra_environment=extra_environment,
                    terminal_columns=20,
                )

                self.assertEqual(plain_tty.returncode, 0, plain_tty.stderr)
                self.assertEqual(plain_tty.stdout.splitlines()[1], "------|-------------")
                self.assertNotIn("\x1b", plain_tty.stdout)
                self.assertIn(description, plain_tty.stdout)

        captured = self.run_cli("show")

        self.assertEqual(captured.returncode, 0, captured.stderr)
        self.assertEqual(
            captured.stdout.splitlines()[1], "------|" + "-" * (len(description) + 1)
        )
        self.assertIn(description, captured.stdout)

    def test_show_colorizes_only_eligible_tty_output(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        self.write_skill(skills, "valid", "name: alpha\ndescription: valid")
        self.write_skill(skills, "warning", "name: warning")
        (skills / "error").mkdir()

        colored = self.run_cli_tty("show")

        self.assertEqual(colored.returncode, 0, colored.stderr)
        self.assertIn("\x1b[1mSKILL\x1b[0m", colored.stdout)
        self.assertIn("\x1b[2m|\x1b[0m", colored.stdout)
        self.assertRegex(colored.stdout, r"\x1b\[2m-+\|-+\x1b\[0m")
        self.assertIn("\x1b[36malpha\x1b[0m", colored.stdout)
        self.assertIn(
            "\x1b[33m[invalid: missing description]\x1b[0m", colored.stdout
        )
        self.assertIn(
            "\x1b[31m[invalid: missing SKILL.md]\x1b[0m", colored.stdout
        )

        plain = self.run_cli("show")

        self.assertNotIn("\x1b", plain.stdout)

    def test_show_tty_color_honors_environment_opt_outs(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        self.write_skill(skills, "valid", "name: alpha\ndescription: valid")
        colored = self.run_cli_tty("show")
        plain = self.run_cli("show").stdout

        self.assertEqual(colored.returncode, 0, colored.stderr)
        self.assertIn("\x1b[36malpha\x1b[0m", colored.stdout)

        for extra_environment in ({"NO_COLOR": "1"}, {"TERM": "dumb"}):
            with self.subTest(environment=extra_environment):
                result = self.run_cli_tty(
                    "show", extra_environment=extra_environment
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, plain)
                self.assertNotIn("\x1b", result.stdout)

    def test_show_dims_empty_tty_message(self):
        self.initialize()

        result = self.run_cli_tty("show")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "\x1b[2mNo skills installed.\x1b[0m\n")

    def test_show_sanitizes_terminal_controls_before_tty_styling(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        declared = "unsafe\x1b]8;;https://example.invalid\x07name"
        self.write_skill(
            skills, "unsafe", f"name: {declared}\ndescription: controlled"
        )

        result = self.run_cli_tty("show")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\x1b]8;;", result.stdout)
        self.assertIn(
            "\x1b[36m"
            r"unsafe\x1b]8;;https://example.invalid\x07name"
            "\x1b[0m",
            result.stdout,
        )

    def test_show_aligns_common_wide_and_combining_skill_names(self):
        self.initialize()
        skills = self.root / "skillsets/default/skills"
        self.write_skill(skills, "wide", "name: 界界界\ndescription: wide")
        combining = "e\u0301" * 6
        self.write_skill(
            skills,
            "combining",
            f"name: {combining}\ndescription: combining",
        )

        result = self.run_cli("show")

        self.assertEqual(
            result.stdout,
            "SKILL  | DESCRIPTION\n"
            "-------|------------\n"
            f"{combining} | combining\n"
            "界界界 | wide\n",
        )

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
            description: >-
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
            self.show_rows(result.stdout),
            [
                ("alpha", "plain description"),
                ("comments", "plain value"),
                ("double", 'first second "quoted" and \\ slash'),
                ("folded", "folded line next line"),
                ("literal", "first line second line"),
                ("multi-double", "first double line second line"),
                ("multi-plain", "first plain line second plain line"),
                ("multi-single", "first single line second single line"),
                ("o'brien", "single 'quoted' description"),
                ("quoted-comment", "kept # hash"),
            ],
        )
        self.assertEqual(result.stderr, "")

    def test_doctor_accepts_chomped_block_scalar_metadata(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        self.write_skill(skills, "chomped", """
            name: chomped
            description: >-
              a folded description
              with trailing-newline chomping
        """)
        self.write_lock(
            self.root / "skillsets" / "default" / ".skill-lock.json",
            {"version": 3, "skills": {"chomped": {}}, "dismissed": {}},
        )

        result = self.run_cli("doctor")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_no_doctor_findings(result)

    def test_show_visibly_escapes_metadata_terminal_controls(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        declared = "café\x1b\x7f\u202eoutil"
        description = "naïve\x1b\x9b\u2066 texte"
        self.write_skill(
            skills,
            "control-display",
            f"name: {declared}\ndescription: {description}",
        )
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("show", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        for raw in ("\x1b", "\x7f", "\x9b", "\u202e", "\u2066"):
            self.assertNotIn(raw, result.stdout)
        self.assertEqual(
            self.show_rows(result.stdout),
            [(r"café\x1b\x7f\u202eoutil", r"naïve\x1b\x9b\u2066 texte")],
        )
        self.assertIn("café", result.stdout)
        self.assertIn("naïve", result.stdout)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

    def test_show_visibly_escapes_invalid_directory_terminal_controls(self):
        self.initialize()
        skills = self.root / "skillsets" / "default" / "skills"
        unsafe_directory = "café\x1b\u2028outil"
        (skills / unsafe_directory).mkdir()
        before = self.filesystem_snapshot(self.home)

        result = self.run_cli("show", "default")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        for raw in ("\x1b", "\u2028"):
            self.assertNotIn(raw, result.stdout)
        self.assertEqual(
            self.show_rows(result.stdout),
            [(r"café\x1b\u2028outil", "[invalid: missing SKILL.md]")],
        )
        self.assertIn("café", result.stdout)
        self.assertEqual(self.filesystem_snapshot(self.home), before)

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
        self.assertIn(
            ("valid-sibling", "remains visible"), self.show_rows(result.stdout)
        )
        for directory, (_contents, category) in invalid.items():
            with self.subTest(directory=directory):
                self.assert_invalid_show_entry(result.stdout, directory, category)
        displayed = [row[0] for row in self.show_rows(result.stdout)]
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
        self.assertIn(
            ("valid", "direct real directory"), self.show_rows(result.stdout)
        )
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
        commands = (("list",), ("codex", "list"), ("current",), ("show", "default"))
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
            ("codex", "list"),
            ("codex", "list", "-v"),
            ("codex", "list", "--verbose"),
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
            ("codex", "list"): "",
            ("current",): "default\n",
            ("show", "default"): "No skills installed.\n",
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
            ("create", "new", "--unknown"),
            ("use",),
            ("rename",),
            ("rename", "old"),
            ("rename", "old", "new", "extra"),
            ("remove",),
            ("remove", "default", "extra"),
            ("remove", "default", "--unknown"),
            ("list", "extra"),
            ("list", "--unknown"),
            ("codex",),
            ("codex", "unknown"),
            ("codex", "enable"),
            ("codex", "disable"),
            ("codex", "list", "extra"),
            ("codex", "list", "--unknown"),
            ("codex", "enable", "default", "--global", "--local"),
            ("codex", "list", "--global", "--local"),
            ("current", "extra"),
            ("current", "--verbose"),
            ("show", "default", "extra"),
            ("doctor", "extra"),
            ("completions",),
            ("completions", "powershell"),
            ("completions", "--powershell"),
            ("completions", "bash", "extra"),
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

    def test_configured_external_directory_supports_complete_lifecycle(self):
        external = self.sandbox / "repository-skillsets"
        external.mkdir()
        self.write_config(self.home, external)

        initialized = self.run_cli("init", "default")
        created = self.run_cli("create", "experiment")
        activated = self.run_cli("use", "experiment")
        renamed = self.run_cli("rename", "default", "baseline")
        removed = self.run_cli("remove", "baseline", "--yes")
        codex_enabled = self.run_cli("codex", "enable", "experiment")
        codex_listed = self.run_cli("codex", "list")
        codex_disabled = self.run_cli("codex", "disable", "experiment")
        inspected = self.run_cli("doctor")

        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(activated.returncode, 0, activated.stderr)
        self.assertEqual(renamed.returncode, 0, renamed.stderr)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(codex_enabled.returncode, 0, codex_enabled.stderr)
        self.assertEqual(codex_listed.stdout, "[g] experiment\n")
        self.assertEqual(codex_disabled.returncode, 0, codex_disabled.stderr)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertTrue((self.root / "skillsets").is_symlink())
        self.assertEqual(os.readlink(self.root / "skillsets"), str(external))
        self.assert_empty_set(self.root, "experiment")
        self.assert_aliases(self.root, "experiment")
        self.assertEqual(self.run_cli("current").stdout, "experiment\n")
        self.assertEqual(self.run_cli("list").stdout, "* experiment\n")
        self.assertFalse(os.path.lexists(external / "default"))
        self.assertFalse(os.path.lexists(external / "baseline"))
        self.assertTrue((external / "experiment").is_dir())
        self.assertFalse(
            os.path.lexists(self.home / ".codex" / "skills" / "experiment")
        )

    def test_configured_init_accepts_other_valid_sets_and_refuses_name_collision(self):
        external = self.sandbox / "shared-skillsets"
        external.mkdir()
        external_root = self.sandbox / "external-root-view"
        external_root.mkdir()
        (external_root / "skillsets").symlink_to(external, target_is_directory=True)
        existing = self.make_set(external_root, "existing")
        marker = existing / "skills" / "keep"
        marker.write_bytes(b"unrelated")
        self.write_config(self.home, external)

        initialized = self.run_cli("init", "default")

        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assertEqual(marker.read_bytes(), b"unrelated")
        self.assertTrue((external / "default").is_dir())

        other_home = self.new_home("configured-collision")
        self.write_config(other_home, external)
        before = self.tree_contract_snapshot(external)
        collision = self.run_cli("init", "existing", home=other_home)

        self.assert_refused(collision)
        self.assertEqual(self.tree_contract_snapshot(external), before)
        self.assertFalse(os.path.lexists(other_home / ".agents" / "skillsets"))

    def test_configured_remove_refuses_a_replaced_managed_link_after_confirmation(self):
        external = self.sandbox / "configured-remove-source"
        victim = self.sandbox / "configured-remove-victim"
        external.mkdir()
        victim.mkdir()
        self.write_config(self.home, external)
        self.assertEqual(self.run_cli("init", "default").returncode, 0)
        self.assertEqual(self.run_cli("create", "doomed").returncode, 0)

        victim_root = self.sandbox / "configured-remove-victim-view"
        victim_root.mkdir()
        (victim_root / "skillsets").symlink_to(victim, target_is_directory=True)
        victim_set = self.make_set(victim_root, "doomed")
        payload = victim_set / "skills" / "keep"
        payload.write_bytes(b"victim data")
        link = self.root / "skillsets"
        fault = self.fault_environment(
            f"""
            import os
            import sys
            from pathlib import Path
            original_stdin = sys.stdin
            link = Path({str(link)!r})
            victim = {str(victim)!r}
            class SwappingStdin:
                def readline(self, *args, **kwargs):
                    link.unlink()
                    os.symlink(victim, link)
                    return "yes\\n"
                def __getattr__(self, name):
                    return getattr(original_stdin, name)
            sys.stdin = SwappingStdin()
            """
        )

        result = self.run_cli("remove", "doomed", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn(
            "configured skillsets link is noncanonical",
            result.stdout + result.stderr,
        )
        self.assertTrue((external / "doomed").is_dir())
        self.assertEqual(payload.read_bytes(), b"victim data")
        self.assertEqual(os.readlink(link), str(victim))

    def test_configured_init_preserves_a_set_created_after_preflight(self):
        external = self.sandbox / "configured-init-race"
        external.mkdir()
        self.write_config(self.home, external)
        target = external / "default"
        payload = target / "skills" / "keep"
        fault = self.fault_environment(
            f"""
            import json
            from pathlib import Path
            target = Path({str(target)!r})
            original_mkdir = Path.mkdir
            injected = False
            def create_collision(path, *args, **kwargs):
                global injected
                if path == target and not injected:
                    injected = True
                    original_mkdir(target)
                    original_mkdir(target / "skills")
                    (target / "skills" / "keep").write_bytes(b"concurrent data")
                    (target / ".skill-lock.json").write_text(
                        json.dumps({EMPTY_LOCK!r}) + "\\n",
                        encoding="utf-8",
                    )
                return original_mkdir(path, *args, **kwargs)
            Path.mkdir = create_collision
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn("File exists", result.stdout + result.stderr)
        self.assertEqual(payload.read_bytes(), b"concurrent data")
        self.assertEqual(
            json.loads((target / ".skill-lock.json").read_text(encoding="utf-8")),
            EMPTY_LOCK,
        )
        self.assertFalse(os.path.lexists(self.root / "skillsets"))

    def test_configured_init_preserves_a_link_and_set_created_after_preflight(self):
        external = self.sandbox / "configured-init-link-race"
        external.mkdir()
        self.write_config(self.home, external)
        link = self.root / "skillsets"
        target = external / "default"
        payload = target / "skills" / "keep"
        fault = self.fault_environment(
            f"""
            import json
            import os
            from pathlib import Path
            link = Path({str(link)!r})
            external = {str(external)!r}
            target = Path({str(target)!r})
            original_symlink = os.symlink
            injected = False
            def create_collision(source, destination, *args, **kwargs):
                global injected
                if Path(destination) == link and not injected:
                    injected = True
                    original_symlink(external, link)
                    target.mkdir()
                    (target / "skills").mkdir()
                    (target / "skills" / "keep").write_bytes(b"concurrent data")
                    (target / ".skill-lock.json").write_text(
                        json.dumps({EMPTY_LOCK!r}) + "\\n",
                        encoding="utf-8",
                    )
                return original_symlink(source, destination, *args, **kwargs)
            os.symlink = create_collision
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn("File exists", result.stdout + result.stderr)
        self.assertEqual(payload.read_bytes(), b"concurrent data")
        self.assertEqual(os.readlink(link), str(external))

    def test_configured_init_rejects_stale_create_staging_without_mutation(self):
        external = self.sandbox / "stale-staging-skillsets"
        staging = external / ".skillset-create-foo.staging"
        staging.mkdir(parents=True)
        marker = staging / "keep"
        marker.write_bytes(b"partially created data")
        self.write_config(self.home, external)
        (self.root / ".skillset.lock").write_text("", encoding="utf-8")
        home_before = self.filesystem_snapshot(self.home)
        external_before = self.filesystem_snapshot(external)

        result = self.run_cli("init", "default")

        self.assert_refused(result)
        self.assertIn(
            f"stale create staging path must be recovered: {staging}",
            result.stdout + result.stderr,
        )
        self.assertEqual(self.filesystem_snapshot(self.home), home_before)
        self.assertEqual(self.filesystem_snapshot(external), external_before)
        self.assertFalse(os.path.lexists(self.root / "skillsets"))

    def test_config_validation_rejects_noncanonical_or_untrusted_sources(self):
        real_source = self.sandbox / "real-config-source"
        real_source.mkdir()
        source_link = self.sandbox / "linked-config-source"
        source_link.symlink_to(real_source, target_is_directory=True)
        cases = (
            ("malformed", None, "{not json\n", "invalid config"),
            (
                "extra-key",
                {
                    "version": 1,
                    "skillsets_directory": str(real_source),
                    "extra": True,
                },
                None,
                "exactly",
            ),
            (
                "wrong-version",
                {"version": 2, "skillsets_directory": str(real_source)},
                None,
                "integer version 1",
            ),
            (
                "relative",
                {"version": 1, "skillsets_directory": "relative/skillsets"},
                None,
                "normalized absolute path",
            ),
            (
                "nonnormalized",
                {
                    "version": 1,
                    "skillsets_directory": str(real_source / ".." / real_source.name),
                },
                None,
                "normalized absolute path",
            ),
            (
                "missing",
                {
                    "version": 1,
                    "skillsets_directory": str(self.sandbox / "missing-source"),
                },
                None,
                "existing real directory",
            ),
            (
                "symlink-source",
                {"version": 1, "skillsets_directory": str(source_link)},
                None,
                "existing real directory",
            ),
        )
        for index, (label, value, raw, expected) in enumerate(cases):
            with self.subTest(label=label):
                home = self.new_home(f"invalid-config-{index}")
                self.write_config(home, real_source, value, raw=raw)
                before = self.tree_contract_snapshot(real_source)

                result = self.run_cli("init", "default", home=home)

                self.assert_refused(result)
                self.assertIn(expected, result.stdout + result.stderr)
                self.assertFalse(os.path.lexists(home / ".agents" / "skillsets"))
                self.assertEqual(self.tree_contract_snapshot(real_source), before)

        symlink_home = self.new_home("symlink-config")
        symlink_root = symlink_home / ".agents"
        symlink_root.mkdir()
        external_config = self.sandbox / "external-config.json"
        external_config.write_text(
            json.dumps(
                {"version": 1, "skillsets_directory": str(real_source)}
            )
            + "\n",
            encoding="utf-8",
        )
        (symlink_root / "config.json").symlink_to(external_config)

        result = self.run_cli("init", "default", home=symlink_home)

        self.assert_refused(result)
        self.assertIn("config must be a real regular file", result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(symlink_root / "skillsets"))

        nested_home = self.new_home("nested-config-source")
        nested_source = nested_home / ".agents" / "external"
        nested_source.mkdir(parents=True)
        self.write_config(nested_home, nested_source)

        result = self.run_cli("init", "default", home=nested_home)

        self.assert_refused(result)
        self.assertIn(
            "configured skillsets directory must be outside the managed root",
            result.stdout + result.stderr,
        )
        self.assertFalse(os.path.lexists(nested_home / ".agents" / "skillsets"))

        linked_parent_home = self.new_home("linked-parent-config-source")
        linked_parent_root = linked_parent_home / ".agents"
        nested_source = linked_parent_root / "external"
        nested_source.mkdir(parents=True)
        root_alias = self.sandbox / "managed-root-alias"
        root_alias.symlink_to(linked_parent_root, target_is_directory=True)
        linked_source = root_alias / "external"
        self.write_config(linked_parent_home, linked_source)

        result = self.run_cli("init", "default", home=linked_parent_home)

        self.assert_refused(result)
        self.assertIn(
            "configured skillsets directory must resolve outside the managed root",
            result.stdout + result.stderr,
        )
        self.assertFalse(os.path.lexists(linked_parent_root / "skillsets"))
        self.assertFalse(os.path.lexists(nested_source / "default"))

    def test_configured_init_rolls_back_owned_link_and_set_after_interruptions(self):
        for index, failure_point in enumerate(("skillsets-link", "initial-set")):
            with self.subTest(failure_point=failure_point):
                home = self.new_home(f"configured-rollback-{index}")
                root = home / ".agents"
                external = self.sandbox / f"rollback-source-{index}"
                external.mkdir()
                unrelated = external / "unrelated"
                (unrelated / "skills").mkdir(parents=True)
                self.write_lock(unrelated / ".skill-lock.json")
                marker = unrelated / "skills" / "keep"
                marker.write_bytes(b"preserve")
                self.write_config(home, external)
                (root / "skills" / "alpha").mkdir(parents=True)
                payload = b"original skill\n"
                (root / "skills" / "alpha" / "SKILL.md").write_bytes(payload)
                lock_bytes = b'{"version": 3, "skills": {}, "dismissed": {}}\n'
                (root / ".skill-lock.json").write_bytes(lock_bytes)
                if failure_point == "skillsets-link":
                    fault = self.fault_environment(
                        f"""
                        import os
                        destination = {str(root / 'skillsets')!r}
                        original_symlink = os.symlink
                        def interrupt_after_link(source, target, *args, **kwargs):
                            result = original_symlink(source, target, *args, **kwargs)
                            if os.path.abspath(os.fspath(target)) == destination:
                                raise KeyboardInterrupt
                            return result
                        os.symlink = interrupt_after_link
                        """
                    )
                else:
                    fault = self.fault_environment(
                        f"""
                        import os
                        from pathlib import Path
                        destination = {str(external / 'default')!r}
                        original_mkdir = Path.mkdir
                        def interrupt_after_set(path, *args, **kwargs):
                            result = original_mkdir(path, *args, **kwargs)
                            if os.path.abspath(os.fspath(path)) == destination:
                                raise KeyboardInterrupt
                            return result
                        Path.mkdir = interrupt_after_set
                        """
                    )

                result = self.run_cli(
                    "init", "default", home=home, extra_environment=fault
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(os.path.lexists(root / "skillsets"))
                self.assertFalse(os.path.lexists(root / "active"))
                self.assertFalse((root / "skills").is_symlink())
                self.assertEqual(
                    (root / "skills" / "alpha" / "SKILL.md").read_bytes(), payload
                )
                self.assertFalse((root / ".skill-lock.json").is_symlink())
                self.assertEqual((root / ".skill-lock.json").read_bytes(), lock_bytes)
                self.assertFalse(os.path.lexists(external / "default"))
                self.assertEqual(marker.read_bytes(), b"preserve")
                self.assertTrue(external.is_dir())

    def test_configured_init_rollback_never_traverses_a_replaced_link(self):
        external = self.sandbox / "rollback-replaced-link-source"
        victim = self.sandbox / "rollback-replaced-link-victim"
        external.mkdir()
        victim.mkdir()
        victim_root = self.sandbox / "rollback-replaced-link-victim-view"
        victim_root.mkdir()
        (victim_root / "skillsets").symlink_to(victim, target_is_directory=True)
        victim_set = self.make_set(victim_root, "default")
        payload = victim_set / "skills" / "keep"
        payload.write_bytes(b"victim data")
        self.write_config(self.home, external)
        link = self.root / "skillsets"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            link = Path({str(link)!r})
            victim = {str(victim)!r}
            original_symlink = os.symlink
            def replace_after_link(source, target, *args, **kwargs):
                result = original_symlink(source, target, *args, **kwargs)
                if Path(target) == link:
                    link.unlink()
                    original_symlink(victim, link)
                    raise KeyboardInterrupt
                return result
            os.symlink = replace_after_link
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn("rollback was incomplete", result.stdout + result.stderr)
        self.assertEqual(payload.read_bytes(), b"victim data")
        self.assertFalse(os.path.lexists(external / "default"))
        self.assertEqual(os.readlink(link), str(victim))

    def test_configured_init_refuses_a_link_replaced_after_creation(self):
        external = self.sandbox / "init-replaced-link-source"
        victim = self.sandbox / "init-replaced-link-victim"
        external.mkdir()
        victim.mkdir()
        victim_root = self.sandbox / "init-replaced-link-victim-view"
        victim_root.mkdir()
        (victim_root / "skillsets").symlink_to(victim, target_is_directory=True)
        victim_set = self.make_set(victim_root, "default")
        payload = victim_set / "skills" / "keep"
        payload.write_bytes(b"victim data")
        self.write_config(self.home, external)
        link = self.root / "skillsets"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            link = Path({str(link)!r})
            victim = {str(victim)!r}
            original_symlink = os.symlink
            def replace_after_link(source, target, *args, **kwargs):
                result = original_symlink(source, target, *args, **kwargs)
                if Path(target) == link:
                    link.unlink()
                    original_symlink(victim, link)
                return result
            os.symlink = replace_after_link
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn(
            "configured skillsets link is noncanonical",
            result.stdout + result.stderr,
        )
        self.assertIn("rollback was incomplete", result.stdout + result.stderr)
        self.assertEqual(payload.read_bytes(), b"victim data")
        self.assertFalse(os.path.lexists(external / "default"))
        self.assertEqual(os.readlink(link), str(victim))
        self.assertFalse(os.path.lexists(self.root / "active"))
        self.assertFalse(os.path.lexists(self.root / "skills"))
        self.assertFalse(os.path.lexists(self.root / ".skill-lock.json"))

    def test_configured_init_refuses_a_link_replaced_during_alias_creation(self):
        external = self.sandbox / "init-alias-replaced-link-source"
        victim = self.sandbox / "init-alias-replaced-link-victim"
        external.mkdir()
        victim.mkdir()
        victim_root = self.sandbox / "init-alias-replaced-link-victim-view"
        victim_root.mkdir()
        (victim_root / "skillsets").symlink_to(victim, target_is_directory=True)
        victim_set = self.make_set(victim_root, "default")
        payload = victim_set / "skills" / "keep"
        payload.write_bytes(b"victim data")
        self.write_config(self.home, external)
        link = self.root / "skillsets"
        active = self.root / "active"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            link = Path({str(link)!r})
            active = Path({str(active)!r})
            victim = {str(victim)!r}
            original_symlink = os.symlink
            def replace_during_aliases(source, target, *args, **kwargs):
                result = original_symlink(source, target, *args, **kwargs)
                if Path(target) == active:
                    link.unlink()
                    original_symlink(victim, link)
                return result
            os.symlink = replace_during_aliases
            """
        )

        result = self.run_cli("init", "default", extra_environment=fault)

        self.assert_refused(result)
        self.assertIn(
            "configured skillsets link is noncanonical",
            result.stdout + result.stderr,
        )
        self.assertIn("rollback was incomplete", result.stdout + result.stderr)
        self.assertEqual(payload.read_bytes(), b"victim data")
        self.assertFalse(os.path.lexists(external / "default"))
        self.assertEqual(os.readlink(link), str(victim))
        self.assertFalse(os.path.lexists(self.root / "active"))
        self.assertFalse(os.path.lexists(self.root / "skills"))
        self.assertFalse(os.path.lexists(self.root / ".skill-lock.json"))

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

    def test_init_rejects_stale_active_staging_without_mutation(self):
        self.root.mkdir()
        (self.root / ".skillset.lock").write_text("", encoding="utf-8")
        staging = self.root / ".skillset-use.staging"
        staging.write_text("foreign staging data", encoding="utf-8")
        before = self.tree_contract_snapshot(self.root)

        result = self.run_cli("init", "default")

        self.assert_refused(result)
        self.assertIn(str(staging), result.stdout + result.stderr)
        self.assertEqual(self.tree_contract_snapshot(self.root), before)
        self.assertFalse(os.path.lexists(self.root / "skillsets"))
        self.assertFalse(os.path.lexists(self.root / "active"))

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

    def test_manual_skillset_creation_activation_and_display(self):
        self.initialize()

        created = self.run_cli("create", "--manual", "personal")
        self.assertEqual(created.returncode, 0, created.stderr)
        personal = self.root / "skillsets" / "personal"
        self.assertTrue((personal / "skills").is_dir())
        self.assertTrue((personal / ".skillset-manual").is_file())
        self.assertEqual((personal / ".skillset-manual").stat().st_size, 0)
        self.assertFalse(os.path.lexists(personal / ".skill-lock.json"))
        self.assertEqual(self.run_cli("list").stdout, "* default\npersonal [m]\n")
        verbose = self.run_cli("list", "--verbose")
        self.assertEqual(verbose.returncode, 0, verbose.stderr)
        verbose_lines = verbose.stdout.splitlines()
        self.assertIn("personal [m]", verbose.stdout)
        self.assertEqual(
            {line.index("|") for line in verbose_lines if "|" in line},
            {verbose_lines[0].index("|")},
        )
        self.assertEqual(
            self.run_cli("show", "personal").stdout,
            "Manual skillset [m]: no upstream lock metadata.\nNo skills installed.\n",
        )

        activated = self.run_cli("use", "personal")
        self.assertEqual(activated.returncode, 0, activated.stderr)
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/personal")
        self.assertEqual(os.readlink(self.root / ".skill-lock.json"), "../.skillset-manual-empty-lock.json")
        sentinel = self.home / ".skillset-manual-empty-lock.json"
        self.assertEqual(json.loads(sentinel.read_text(encoding="utf-8")), EMPTY_LOCK)
        self.assertEqual(stat.S_IMODE(sentinel.stat().st_mode), 0o444)
        self.assertEqual(self.run_cli("list").stdout, "default\n* personal [m]\n")
        tty = self.run_cli_tty("list")
        self.assertEqual(tty.returncode, 0, tty.stderr)
        self.assertIn("\x1b[33m[m]\x1b[0m", tty.stdout)

        sentinel.chmod(0o644)
        sentinel.unlink()
        recreated = self.run_cli("use", "personal")
        self.assertEqual(recreated.returncode, 0, recreated.stderr)
        self.assertEqual(stat.S_IMODE(sentinel.stat().st_mode), 0o444)

        sentinel.chmod(0o644)
        sentinel.unlink()
        repaired = self.run_cli("doctor", "--fix", input_text="yes\n")
        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertEqual(stat.S_IMODE(sentinel.stat().st_mode), 0o444)
        mutually_exclusive = self.run_cli(
            "create", "--manual", "--from", "default", "invalid"
        )
        self.assertEqual(mutually_exclusive.returncode, 2)

    def test_manual_classification_rejects_marker_and_lock_misconfigurations(self):
        cases = ("unmarked", "both", "nonempty-marker", "symlink-marker")
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                home = self.new_home(f"manual-classification-{index}")
                root = self.make_managed_layout(home)
                target = root / "skillsets" / "broken"
                (target / "skills").mkdir(parents=True)
                if case == "both":
                    (target / ".skillset-manual").touch()
                    self.write_lock(target / ".skill-lock.json")
                elif case == "nonempty-marker":
                    (target / ".skillset-manual").write_text("not empty", encoding="utf-8")
                elif case == "symlink-marker":
                    external = home / "marker"
                    external.touch()
                    (target / ".skillset-manual").symlink_to(external)

                result = self.run_cli("use", "broken", home=home)
                self.assert_refused(result)
                self.assertEqual(os.readlink(root / "active"), "skillsets/default")

    def test_manual_clone_preserves_mode_and_lock_aware_delegation_refuses_before_npx(self):
        self.initialize()
        self.assertEqual(self.run_cli("create", "--manual", "personal").returncode, 0)
        source = self.root / "skillsets" / "personal"
        (source / "skills" / "handwritten").mkdir()
        cloned = self.run_cli("create", "copy", "--from", "personal")
        self.assertEqual(cloned.returncode, 0, cloned.stderr)
        copy = self.root / "skillsets" / "copy"
        self.assertTrue((copy / ".skillset-manual").is_file())
        self.assertFalse(os.path.lexists(copy / ".skill-lock.json"))
        self.assertTrue((copy / "skills" / "handwritten").is_dir())

        self.assertEqual(self.run_cli("use", "personal").returncode, 0)
        environment, record = self.fake_npx_environment()
        refused = self.run_cli("skills", "update", extra_environment=environment)
        self.assert_refused(refused)
        self.assertIn("manually managed", refused.stderr)
        self.assertFalse(record.exists())
        passed = self.run_cli("skills", "find", "handwritten", extra_environment=environment)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assert_fake_argv(record, ["skills", "find", "handwritten"])

    def test_doctor_fix_completes_verified_interrupted_manual_activation(self):
        self.initialize()
        self.assertEqual(self.run_cli("create", "--manual", "personal").returncode, 0)
        fault = self.fault_environment(f"""
            import os
            target = {str(self.root / 'active')!r}
            original_replace = os.replace
            def fail_after_active(source, destination, *args, **kwargs):
                result = original_replace(source, destination, *args, **kwargs)
                if os.path.abspath(os.fspath(destination)) == target:
                    raise OSError("injected interruption after active replacement")
                return result
            os.replace = fail_after_active
        """)
        interrupted = self.run_cli("use", "personal", extra_environment=fault)
        self.assert_refused(interrupted)
        self.assertTrue(os.path.lexists(self.root / ".skillset-use.staging"))
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/personal")
        self.assertEqual(os.readlink(self.root / ".skill-lock.json"), "active/.skill-lock.json")

        repaired = self.run_cli("doctor", "--fix", input_text="yes\n")
        self.assertEqual(repaired.returncode, 0, repaired.stderr)
        self.assertEqual(os.readlink(self.root / ".skill-lock.json"), "../.skillset-manual-empty-lock.json")
        self.assertFalse(os.path.lexists(self.root / ".skillset-use.staging"))

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

    def test_create_use_activates_with_options_before_and_after_name(self):
        cases = (
            ("empty-after", ("create", "empty-after", "--use"), False),
            ("empty-before", ("create", "--use", "empty-before"), False),
            ("clone-after", ("create", "clone-after", "--from", "default", "--use"), True),
            ("clone-before", ("create", "--use", "--from", "default", "clone-before"), True),
            ("clone-short", ("create", "clone-short", "-f", "default", "--use"), True),
        )
        for index, (name, arguments, cloned) in enumerate(cases):
            home = self.new_home(f"create-use-{index}")
            root = self.make_managed_layout(home)
            source = root / "skillsets" / "default"
            (source / "skills" / "source-marker").write_bytes(b"source payload")
            lock_bytes = b'{"version":3,"skills":{},"dismissed":{}}\n'
            (source / ".skill-lock.json").write_bytes(lock_bytes)
            result = self.run_cli(*arguments, home=home)
            with self.subTest(arguments=arguments):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_aliases(root, name)
                target = root / "skillsets" / name
                if cloned:
                    self.assertEqual(
                        (target / "skills" / "source-marker").read_bytes(),
                        b"source payload",
                    )
                    self.assertEqual((target / ".skill-lock.json").read_bytes(), lock_bytes)
                else:
                    self.assert_empty_set(root, name)

    def test_create_use_creation_failure_does_not_change_active_set(self):
        self.initialize()
        occupied = self.make_set(self.root, "occupied")
        marker = occupied / "skills" / "keep"
        marker.write_bytes(b"untouched")
        result = self.run_cli("create", "occupied", "--use")
        self.assert_refused(result)
        self.assertEqual(marker.read_bytes(), b"untouched")
        self.assert_aliases(self.root, "default")

    def test_create_use_activation_failure_keeps_new_set_and_previous_active(self):
        self.initialize()
        fault = self.fault_environment(f"""
            import os
            active = {str(self.root / 'active')!r}
            original_replace = os.replace
            def fail_active(source, destination, *args, **kwargs):
                if os.path.abspath(os.fspath(destination)) == active:
                    raise OSError("injected activation failure")
                return original_replace(source, destination, *args, **kwargs)
            os.replace = fail_active
        """)
        stable = {name: os.readlink(self.root / name)
                  for name in ("active", "skills", ".skill-lock.json")}
        result = self.run_cli("create", "experiment", "--use", extra_environment=fault)
        self.assert_refused(result)
        self.assert_empty_set(self.root, "experiment")
        self.assertEqual({name: os.readlink(self.root / name) for name in stable}, stable)
        self.assertTrue(os.path.lexists(self.root / ".skillset-use.staging"))

    def test_create_use_post_replace_failure_preserves_committed_activation(self):
        self.initialize()
        fault = self.fault_environment(f"""
            import os
            active = {str(self.root / 'active')!r}
            original_replace = os.replace
            def fail_after_active(source, destination, *args, **kwargs):
                result = original_replace(source, destination, *args, **kwargs)
                if os.path.abspath(os.fspath(destination)) == active:
                    raise OSError("injected post-replacement failure")
                return result
            os.replace = fail_after_active
        """)
        result = self.run_cli("create", "experiment", "--use", extra_environment=fault)
        self.assert_refused(result)
        self.assert_empty_set(self.root, "experiment")
        self.assert_aliases(self.root, "experiment")
        self.assertTrue(os.path.lexists(self.root / ".skillset-use.staging"))

    def test_create_help_documents_create_options(self):
        result = self.run_cli("create", "--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-f SOURCE", result.stdout)
        self.assertIn("--from SOURCE", result.stdout)
        self.assertIn("clone from an existing skillset", result.stdout)
        self.assertIn("--use", result.stdout)

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

    def test_rename_inactive_set_preserves_complete_tree_and_active_alias(self):
        self.initialize()
        source = self.make_set(self.root, "old")
        source.chmod(0o750)
        nested = source / "skills" / "alpha" / "nested"
        nested.mkdir(parents=True)
        nested.chmod(0o711)
        executable = nested / "tool"
        executable.write_bytes(b"#!/bin/sh\nprintf preserved\\n\n")
        executable.chmod(0o751)
        (nested / "tool-link").symlink_to("tool")
        lock_bytes = b'{"version":3,"skills":{"alpha":{}},"dismissed":{}}\n'
        (source / ".skill-lock.json").write_bytes(lock_bytes)
        expected_tree = self.tree_contract_snapshot(source)
        source_inode = source.stat().st_ino
        aliases_before = {
            name: ((self.root / name).lstat().st_ino, os.readlink(self.root / name))
            for name in ("active", "skills", ".skill-lock.json")
        }

        result = self.run_cli("rename", "old", "new")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertFalse(os.path.lexists(source))
        destination = self.root / "skillsets" / "new"
        self.assertEqual(destination.stat().st_ino, source_inode)
        self.assertEqual(self.tree_contract_snapshot(destination), expected_tree)
        self.assertEqual(
            {
                name: ((self.root / name).lstat().st_ino, os.readlink(self.root / name))
                for name in aliases_before
            },
            aliases_before,
        )

    def test_rename_active_set_retargets_only_active_and_updates_inspection(self):
        self.initialize("old")
        payload = self.root / "skillsets" / "old" / "skills" / "payload.bin"
        payload.write_bytes(b"active rename payload\x00\xff")
        stable_aliases = {
            name: ((self.root / name).lstat().st_ino, os.readlink(self.root / name))
            for name in ("skills", ".skill-lock.json")
        }

        result = self.run_cli("rename", "old", "new")
        current = self.run_cli("current")
        listed = self.run_cli("list")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "old"))
        self.assertEqual(
            (self.root / "skillsets" / "new" / "skills" / "payload.bin").read_bytes(),
            b"active rename payload\x00\xff",
        )
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/new")
        for name, identity in stable_aliases.items():
            self.assertEqual(
                ((self.root / name).lstat().st_ino, os.readlink(self.root / name)),
                identity,
            )
        self.assertEqual((current.returncode, current.stdout, current.stderr), (0, "new\n", ""))
        self.assertEqual((listed.returncode, listed.stdout, listed.stderr), (0, "* new\n", ""))

    def test_rename_rejects_missing_source_and_invalid_names_without_mutation(self):
        self.initialize()
        self.make_set(self.root, "old")
        before = self.tree_contract_snapshot(self.root / "skillsets")

        missing = self.run_cli("rename", "missing", "new")
        self.assert_refused(missing)
        invalid_cases = (
            ("../escape", "new"),
            ("Upper", "new"),
            ("old", "../escape"),
            ("old", ".hidden"),
            ("old", "two words"),
        )
        for old, new in invalid_cases:
            with self.subTest(old=old, new=new):
                result = self.run_cli("rename", old, new)
                self.assert_refused(result)
        self.assertEqual(
            self.tree_contract_snapshot(self.root / "skillsets"), before
        )
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/default")

    def test_rename_refuses_directory_file_and_symlink_collisions_without_overwrite(self):
        for index, kind in enumerate(("directory", "file", "symlink")):
            home = self.new_home(f"rename-collision-{index}")
            root = self.make_managed_layout(home)
            source = self.make_set(root, "old")
            (source / "skills" / "source-marker").write_bytes(b"source")
            destination = root / "skillsets" / "new"
            external = home / "external-target"
            if kind == "directory":
                target = self.make_set(root, "new")
                (target / "skills" / "keep").write_bytes(b"directory target")
            elif kind == "file":
                destination.write_bytes(b"file target")
            else:
                external.mkdir()
                (external / "keep").write_bytes(b"symlink target")
                destination.symlink_to(external, target_is_directory=True)
            source_before = self.tree_contract_snapshot(source)
            target_before = self.tree_contract_snapshot(destination)
            external_before = (
                self.tree_contract_snapshot(external) if external.exists() else None
            )

            with self.subTest(kind=kind):
                result = self.run_cli("rename", "old", "new", home=home)
                self.assert_refused(result)
                self.assertEqual(self.tree_contract_snapshot(source), source_before)
                self.assertEqual(
                    self.tree_contract_snapshot(destination), target_before
                )
                if external_before is not None:
                    self.assertEqual(
                        self.tree_contract_snapshot(external), external_before
                    )

    def test_rename_and_remove_refuse_uninitialized_and_invalid_layouts(self):
        for index, arguments in enumerate(
            (("rename", "old", "new"), ("remove", "old", "--yes"))
        ):
            home = self.new_home(f"lifecycle-uninitialized-{index}")
            result = self.run_cli(*arguments, home=home)
            with self.subTest(layout="uninitialized", command=arguments[0]):
                self.assert_refused(result)

        root = self.make_managed_layout(self.new_home("lifecycle-invalid"))
        (root / ".skillset.lock").write_text("", encoding="utf-8")
        self.make_set(root, "old")
        (root / "skills").unlink()
        (root / "skills").symlink_to("skillsets/default/skills")
        before = self.tree_contract_snapshot(root)
        for arguments in (("rename", "old", "new"), ("remove", "old", "--yes")):
            with self.subTest(layout="invalid", command=arguments[0]):
                result = self.run_cli(*arguments, home=root.parent)
                self.assert_refused(result)
                self.assertNotIn("Remove skillset", result.stderr)
                self.assertEqual(self.tree_contract_snapshot(root), before)

    def test_lifecycle_paths_refuse_source_symlinks_and_cannot_escape_skillsets(self):
        home = self.new_home("lifecycle-containment")
        root = self.make_managed_layout(home)
        external_set = home / "external-set"
        (external_set / "skills").mkdir(parents=True)
        self.write_lock(external_set / ".skill-lock.json")
        external_marker = external_set / "skills" / "keep"
        external_marker.write_bytes(b"external set untouched")
        (root / "skillsets" / "linked").symlink_to(
            external_set, target_is_directory=True
        )
        outside = root / "escape"
        outside.mkdir()
        outside_marker = outside / "keep"
        outside_marker.write_bytes(b"outside untouched")
        external_before = self.tree_contract_snapshot(external_set)
        outside_before = self.tree_contract_snapshot(outside)

        symlink_cases = (
            ("rename", "linked", "new"),
            ("remove", "linked", "--yes"),
        )
        for arguments in symlink_cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, home=home)
                self.assert_refused(result)
                self.assertNotIn("Remove skillset", result.stderr)
                self.assertEqual(
                    self.tree_contract_snapshot(external_set), external_before
                )
        self.assertTrue((root / "skillsets" / "linked").is_symlink())
        (root / "skillsets" / "linked").unlink()

        traversal_cases = (
            ("rename", "../escape", "new"),
            ("rename", "default", "../escape"),
            ("remove", "../escape", "--yes"),
        )
        for arguments in traversal_cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, home=home)
                self.assert_refused(result)
                self.assertNotIn("Remove skillset", result.stderr)
                self.assertEqual(
                    self.tree_contract_snapshot(external_set), external_before
                )
                self.assertEqual(self.tree_contract_snapshot(outside), outside_before)

    def test_lifecycle_operations_refuse_stale_active_staging_without_mutation(self):
        cases = (
            ("inactive-rename", ("rename", "old", "new")),
            ("active-rename", ("rename", "default", "renamed")),
            ("remove", ("remove", "victim", "--yes")),
        )
        for index, (label, arguments) in enumerate(cases):
            home = self.new_home(f"lifecycle-stale-{index}")
            root = self.make_managed_layout(home)
            (root / ".skillset.lock").write_text("", encoding="utf-8")
            self.make_set(root, "old")
            self.make_set(root, "victim")
            staging = root / ".skillset-use.staging"
            staging.write_text("foreign staging data", encoding="utf-8")
            before = self.tree_contract_snapshot(root)

            with self.subTest(label=label):
                result = self.run_cli(*arguments, home=home)
                self.assert_refused(result)
                self.assertIn(str(staging), result.stdout + result.stderr)
                self.assertNotIn("Remove skillset", result.stderr)
                self.assertEqual(self.tree_contract_snapshot(root), before)

    def test_active_rename_retarget_failure_rolls_directory_back_and_cleans_staging(self):
        self.initialize("old")
        payload = self.root / "skillsets" / "old" / "skills" / "keep"
        payload.write_bytes(b"recoverable payload")
        old = str(self.root / "skillsets" / "old")
        new = str(self.root / "skillsets" / "new")
        active = str(self.root / "active")
        staging = self.root / ".skillset-use.staging"
        reached = self.sandbox / "rename-retarget-reached"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            old = {old!r}
            new = {new!r}
            active = {active!r}
            reached = Path({str(reached)!r})
            original_replace = os.replace
            def fail_active(source, destination, *args, **kwargs):
                if os.path.abspath(os.fspath(destination)) == active:
                    if os.path.lexists(old) or not os.path.isdir(new):
                        raise AssertionError("active retarget preceded directory rename")
                    reached.write_text(os.fspath(source), encoding="utf-8")
                    raise OSError("injected active retarget failure")
                return original_replace(source, destination, *args, **kwargs)
            os.replace = fail_active
            """
        )

        result = self.run_cli("rename", "old", "new", extra_environment=fault)

        self.assert_refused(result)
        self.assertTrue(reached.exists(), "active retarget was not attempted")
        self.assertEqual(Path(reached.read_text(encoding="utf-8")), staging)
        self.assertEqual(payload.read_bytes(), b"recoverable payload")
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "new"))
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/old")
        self.assertFalse(os.path.lexists(staging))

    def test_active_rename_keyboard_interrupt_before_replacement_rolls_back(self):
        self.initialize("old")
        payload = self.root / "skillsets" / "old" / "skills" / "keep"
        payload.write_bytes(b"interrupt payload")
        old = str(self.root / "skillsets" / "old")
        new = str(self.root / "skillsets" / "new")
        active = str(self.root / "active")
        staging = self.root / ".skillset-use.staging"
        reached = self.sandbox / "rename-interrupt-reached"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            old = {old!r}
            new = {new!r}
            active = {active!r}
            reached = Path({str(reached)!r})
            original_replace = os.replace
            def interrupt_active(source, destination, *args, **kwargs):
                if os.path.abspath(os.fspath(destination)) == active:
                    if os.path.lexists(old) or not os.path.isdir(new):
                        raise AssertionError("active retarget preceded directory rename")
                    reached.write_text(os.fspath(source), encoding="utf-8")
                    raise KeyboardInterrupt
                return original_replace(source, destination, *args, **kwargs)
            os.replace = interrupt_active
            """
        )

        result = self.run_cli("rename", "old", "new", extra_environment=fault)

        self.assertEqual(result.returncode, 130, (result.stdout, result.stderr))
        self.assertTrue(reached.exists(), "active retarget was not attempted")
        self.assertEqual(Path(reached.read_text(encoding="utf-8")), staging)
        self.assertEqual(payload.read_bytes(), b"interrupt payload")
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "new"))
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/old")
        self.assertFalse(os.path.lexists(staging))

    def test_active_rename_keyboard_interrupt_after_directory_move_rolls_back(self):
        self.initialize("old")
        payload = self.root / "skillsets" / "old" / "skills" / "keep"
        payload.write_bytes(b"post-move interrupt payload")
        old = str(self.root / "skillsets" / "old")
        new = str(self.root / "skillsets" / "new")
        moved = self.sandbox / "rename-directory-moved"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            old = {old!r}
            new = {new!r}
            moved = Path({str(moved)!r})
            original_rename = os.rename
            interrupted = False
            def interrupt_after_move(source, destination, *args, **kwargs):
                global interrupted
                pair = (os.path.abspath(os.fspath(source)),
                        os.path.abspath(os.fspath(destination)))
                result = original_rename(source, destination, *args, **kwargs)
                if pair == (old, new) and not interrupted:
                    interrupted = True
                    moved.write_text("moved", encoding="utf-8")
                    raise KeyboardInterrupt
                return result
            os.rename = interrupt_after_move
            """
        )

        result = self.run_cli("rename", "old", "new", extra_environment=fault)

        self.assertEqual(result.returncode, 130, (result.stdout, result.stderr))
        self.assertTrue(moved.exists(), "directory rename was not reached")
        self.assertTrue(payload.is_file(), "active directory rename was not rolled back")
        self.assertEqual(payload.read_bytes(), b"post-move interrupt payload")
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "new"))
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/old")
        self.assertFalse(os.path.lexists(self.root / ".skillset-use.staging"))

    def test_active_rename_rollback_failure_reports_paths_and_preserves_staged_data(self):
        self.initialize("old")
        old = self.root / "skillsets" / "old"
        new = self.root / "skillsets" / "new"
        active = self.root / "active"
        (old / "skills" / "only-copy").write_bytes(b"only staged copy")
        expected_tree = self.tree_contract_snapshot(old)
        fault = self.fault_environment(
            f"""
            import os
            old = {str(old)!r}
            new = {str(new)!r}
            active = {str(active)!r}
            renamed = False
            original_rename = os.rename
            original_replace = os.replace
            def paths(source, destination):
                return (os.path.abspath(os.fspath(source)),
                        os.path.abspath(os.fspath(destination)))
            def injected_rename(source, destination, *args, **kwargs):
                global renamed
                pair = paths(source, destination)
                if renamed and pair == (new, old):
                    raise OSError("injected rollback failure")
                result = original_rename(source, destination, *args, **kwargs)
                if pair == (old, new):
                    renamed = True
                return result
            def injected_replace(source, destination, *args, **kwargs):
                global renamed
                pair = paths(source, destination)
                if pair[1] == active:
                    raise OSError("injected active retarget failure")
                if renamed and pair == (new, old):
                    raise OSError("injected rollback failure")
                result = original_replace(source, destination, *args, **kwargs)
                if pair == (old, new):
                    renamed = True
                return result
            os.rename = injected_rename
            os.replace = injected_replace
            """
        )

        result = self.run_cli("rename", "old", "new", extra_environment=fault)

        self.assert_refused(result)
        report = result.stdout + result.stderr
        for path in (old, new, active):
            self.assertIn(str(path), report)
        self.assertIn("doctor", report.lower())
        self.assertFalse(os.path.lexists(old))
        self.assertEqual(self.tree_contract_snapshot(new), expected_tree)
        self.assertEqual(os.readlink(active), "skillsets/old")
        self.assertFalse(os.path.lexists(self.root / ".skillset-use.staging"))

    def test_active_rename_failure_after_replace_leaves_valid_committed_layout(self):
        self.initialize("old")
        payload = self.root / "skillsets" / "old" / "skills" / "only-copy"
        payload.write_bytes(b"committed payload")
        active = str(self.root / "active")
        staging = self.root / ".skillset-use.staging"
        replaced = self.sandbox / "rename-active-replaced"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            active = {active!r}
            replaced = Path({str(replaced)!r})
            original_replace = os.replace
            def fail_after_active_replace(source, destination, *args, **kwargs):
                result = original_replace(source, destination, *args, **kwargs)
                if os.path.abspath(os.fspath(destination)) == active:
                    replaced.write_text(os.fspath(source), encoding="utf-8")
                    raise OSError("injected post-replace failure")
                return result
            os.replace = fail_after_active_replace
            """
        )

        result = self.run_cli("rename", "old", "new", extra_environment=fault)

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertTrue(replaced.exists(), "active replacement was not reached")
        self.assertEqual(Path(replaced.read_text(encoding="utf-8")), staging)
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "old"))
        self.assertEqual(
            (self.root / "skillsets" / "new" / "skills" / "only-copy").read_bytes(),
            b"committed payload",
        )
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/new")
        self.assertFalse(os.path.lexists(staging))
        current = self.run_cli("current")
        listed = self.run_cli("list")
        self.assertEqual((current.returncode, current.stdout), (0, "new\n"))
        self.assertEqual((listed.returncode, listed.stdout), (0, "* new\n"))

    def test_active_rename_keyboard_interrupt_after_replace_keeps_committed_layout(self):
        self.initialize("old")
        payload = self.root / "skillsets" / "old" / "skills" / "only-copy"
        payload.write_bytes(b"interrupt committed payload")
        active = str(self.root / "active")
        replaced = self.sandbox / "rename-active-interrupted-after-replace"
        fault = self.fault_environment(
            f"""
            import os
            from pathlib import Path
            active = {active!r}
            replaced = Path({str(replaced)!r})
            original_replace = os.replace
            def interrupt_after_active_replace(source, destination, *args, **kwargs):
                result = original_replace(source, destination, *args, **kwargs)
                if os.path.abspath(os.fspath(destination)) == active:
                    replaced.write_text("replaced", encoding="utf-8")
                    raise KeyboardInterrupt
                return result
            os.replace = interrupt_after_active_replace
            """
        )

        result = self.run_cli("rename", "old", "new", extra_environment=fault)

        self.assertEqual(result.returncode, 130, (result.stdout, result.stderr))
        self.assertTrue(replaced.exists(), "active replacement was not reached")
        self.assertFalse(os.path.lexists(self.root / "skillsets" / "old"))
        self.assertEqual(
            (self.root / "skillsets" / "new" / "skills" / "only-copy").read_bytes(),
            b"interrupt committed payload",
        )
        self.assertEqual(os.readlink(self.root / "active"), "skillsets/new")
        self.assertFalse(os.path.lexists(self.root / ".skillset-use.staging"))
        current = self.run_cli("current")
        self.assertEqual((current.returncode, current.stdout), (0, "new\n"))

    def test_remove_prompt_is_exact_and_accepts_case_insensitive_y_or_yes(self):
        prompt = "Remove skillset 'victim'? [y/N] "
        for index, response in enumerate(("y\n", "Y\n", "yes\n", "YeS\n")):
            home = self.new_home(f"remove-confirm-{index}")
            root = self.make_managed_layout(home)
            victim = self.make_set(root, "victim")
            (victim / "skills" / "keep").write_bytes(b"removed")

            with self.subTest(response=response.strip()):
                result = self.run_cli(
                    "remove", "victim", home=home, input_text=response
                )
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                self.assertEqual(result.stderr, prompt)
                self.assertFalse(os.path.lexists(victim))

    def test_remove_yes_skips_prompt(self):
        self.initialize()
        victim = self.make_set(self.root, "victim")

        result = self.run_cli("remove", "victim", "--yes")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertNotIn("Remove skillset", result.stderr)
        self.assertFalse(os.path.lexists(victim))

    def test_remove_decline_empty_invalid_and_eof_cancel_without_mutation(self):
        cases = (("decline", "n\n"), ("empty", "\n"), ("invalid", "maybe\n"), ("eof", ""))
        prompt = "Remove skillset 'victim'? [y/N] "
        for index, (label, response) in enumerate(cases):
            home = self.new_home(f"remove-cancel-{index}")
            root = self.make_managed_layout(home)
            victim = self.make_set(root, "victim")
            nested = victim / "skills" / "nested"
            nested.mkdir()
            (nested / "keep").write_bytes(b"preserved")
            before = self.tree_contract_snapshot(victim)

            with self.subTest(label=label):
                result = self.run_cli(
                    "remove", "victim", home=home, input_text=response
                )
                self.assert_refused(result)
                self.assertTrue(result.stderr.startswith(prompt), result.stderr)
                self.assertIn("cancelled", (result.stdout + result.stderr).lower())
                self.assertEqual(self.tree_contract_snapshot(victim), before)

    def test_remove_rejects_active_set_before_prompt_even_with_yes(self):
        self.initialize("active-set")
        active = self.root / "skillsets" / "active-set"
        before = self.tree_contract_snapshot(active)
        cases = (("remove", "active-set"), ("remove", "active-set", "--yes"))

        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments, input_text="yes\n")
                self.assert_refused(result)
                self.assertNotIn("Remove skillset", result.stderr)
                self.assertEqual(self.tree_contract_snapshot(active), before)

    def test_remove_refuses_missing_invalid_symlink_and_invalid_layout_before_prompt(self):
        prompt = "Remove skillset"
        self.initialize()
        victim = self.make_set(self.root, "victim")
        before = self.tree_contract_snapshot(victim)
        for name in ("missing", "../escape", "Upper", ".hidden", "two words"):
            with self.subTest(case="name", name=name):
                result = self.run_cli("remove", name, input_text="yes\n")
                self.assert_refused(result)
                self.assertNotIn(prompt, result.stderr)
                self.assertEqual(self.tree_contract_snapshot(victim), before)

        symlink_home = self.new_home("remove-symlink")
        symlink_root = self.make_managed_layout(symlink_home)
        external = symlink_home / "external"
        (external / "skills").mkdir(parents=True)
        self.write_lock(external / ".skill-lock.json")
        marker = external / "skills" / "keep"
        marker.write_bytes(b"external")
        (symlink_root / "skillsets" / "linked").symlink_to(
            external, target_is_directory=True
        )
        external_before = self.tree_contract_snapshot(external)
        result = self.run_cli(
            "remove", "linked", home=symlink_home, input_text="yes\n"
        )
        self.assert_refused(result)
        self.assertNotIn(prompt, result.stderr)
        self.assertEqual(self.tree_contract_snapshot(external), external_before)
        self.assertTrue((symlink_root / "skillsets" / "linked").is_symlink())

        invalid_home = self.new_home("remove-invalid-layout")
        invalid_root = self.make_managed_layout(invalid_home)
        invalid_victim = self.make_set(invalid_root, "victim")
        (invalid_root / ".skill-lock.json").unlink()
        (invalid_root / ".skill-lock.json").symlink_to(
            "skillsets/default/.skill-lock.json"
        )
        invalid_before = self.tree_contract_snapshot(invalid_victim)
        result = self.run_cli(
            "remove", "victim", home=invalid_home, input_text="yes\n"
        )
        self.assert_refused(result)
        self.assertNotIn(prompt, result.stderr)
        self.assertEqual(self.tree_contract_snapshot(invalid_victim), invalid_before)

    def test_remove_nested_tree_succeeds_without_following_external_links(self):
        self.initialize()
        victim = self.make_set(self.root, "victim")
        nested = victim / "skills" / "alpha" / "one" / "two"
        nested.mkdir(parents=True)
        (nested / "payload").write_bytes(b"nested payload")
        external = self.home / "external-tree"
        external.mkdir()
        marker = external / "keep"
        marker.write_bytes(b"must survive")
        (victim / "skills" / "external-link").symlink_to(
            external, target_is_directory=True
        )
        external_before = self.tree_contract_snapshot(external)

        result = self.run_cli("remove", "victim", "--yes")

        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertFalse(os.path.lexists(victim))
        self.assertEqual(self.tree_contract_snapshot(external), external_before)

    def test_rename_and_remove_wait_for_advisory_lock_with_markers(self):
        self.initialize()
        self.make_set(self.root, "old")
        self.make_set(self.root, "victim")
        cases = (("rename", "old", "new"), ("remove", "victim", "--yes"))
        lock_path = self.root / ".skillset.lock"

        for index, arguments in enumerate(cases):
            attempted = self.sandbox / f"lifecycle-lock-attempted-{index}"
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
            with self.subTest(command=arguments[0]):
                with lock_path.open("a+") as lock_file:
                    fcntl.flock(lock_file, fcntl.LOCK_EX)
                    process = self.popen_cli(
                        *arguments, extra_environment=fault
                    )
                    try:
                        self.wait_for_path(attempted, process)
                        self.assertIsNone(
                            process.poll(), f"{arguments} did not wait for lock"
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

    def test_remove_confirmation_waits_while_holding_advisory_lock(self):
        self.initialize()
        victim = self.make_set(self.root, "victim")
        lock_acquired = self.sandbox / "remove-confirm-lock-acquired"
        input_started = self.sandbox / "remove-confirm-input-started"
        fault = self.fault_environment(
            f"""
            import fcntl
            import sys
            from pathlib import Path
            acquired = Path({str(lock_acquired)!r})
            reading = Path({str(input_started)!r})
            original_flock = fcntl.flock
            def marked_flock(file, operation):
                result = original_flock(file, operation)
                if operation & fcntl.LOCK_EX:
                    acquired.write_text("acquired", encoding="utf-8")
                return result
            class MarkedInput:
                def __init__(self, wrapped):
                    self.wrapped = wrapped
                def __getattr__(self, name):
                    return getattr(self.wrapped, name)
                def read(self, *args, **kwargs):
                    reading.write_text("read", encoding="utf-8")
                    return self.wrapped.read(*args, **kwargs)
                def readline(self, *args, **kwargs):
                    reading.write_text("readline", encoding="utf-8")
                    return self.wrapped.readline(*args, **kwargs)
            fcntl.flock = marked_flock
            sys.stdin = MarkedInput(sys.stdin)
            """
        )
        process = self.popen_cli(
            "remove",
            "victim",
            extra_environment=fault,
            stdin=subprocess.PIPE,
        )
        try:
            self.wait_for_path(input_started, process)
            self.assertTrue(lock_acquired.exists(), "confirmation began before locking")
            self.assertIsNone(process.poll(), "confirmation did not wait for input")
            with (self.root / ".skillset.lock").open("a+") as probe:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stdout, stderr = process.communicate("yes\n", timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)

        self.assertEqual(process.returncode, 0, (stdout, stderr))
        self.assertEqual(stderr, "Remove skillset 'victim'? [y/N] ")
        self.assertFalse(os.path.lexists(victim))

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
        self.assertIn("doctor", report.lower())


if __name__ == "__main__":
    unittest.main()
