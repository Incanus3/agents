# `skillset` Shell Completions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lock-free `skillset completions SHELL` command that emits native Bash, Zsh, or Fish completion scripts
with static wrapper grammar and dynamic existing-skillset candidates.

**Architecture:** Keep shell source in a focused `lib/skillset/completions.py` module and add one early-return dispatch
path in `lib/skillset/cli.py`. The generated scripts encode shell-native completion rules and call public
`skillset list` only when an existing managed name is valid.

**Source of truth:** `docs/specs/2026-07-11-skillset-shell-completions-design.md`

**Tracking:** `agents-ph3`

**Tech stack:** Python 3 standard library, `argparse`, Bash completion builtins, Zsh completion functions, Fish
`complete`, and black-box `unittest` tests.

## Global constraints

- Support exactly `bash`, `zsh`, and `fish`; add no runtime dependency.
- A valid invocation emits one deterministic script, writes no stderr, ends with one newline, and exits 0.
- Dispatch completion generation before root resolution, layout validation, and both locks.
- Keep every existing command's parsing, validation, locking, output, and exit behavior unchanged.
- Complete public wrapper commands/options and context-sensitive existing skillset names.
- Leave arguments after `skillset skills` opaque and disable accidental file completion.
- Query names through `skillset list`, suppress lookup stderr, and treat lookup failure as no candidates.
- Keep production surfaces free of planning and tracker terminology.
- Do not commit, change bead status, or close the bead without explicit user permission.
- If any Jujutsu command reports that the working copy is stale, stop immediately and ask the user to resolve it.

## File map

- Create `lib/skillset/completions.py`: own immutable shell templates and `emit_completions(shell, output=None)`.
- Modify `lib/skillset/cli.py`: add parser grammar and dispatch the command before all lock acquisition.
- Modify `tests/test_skillset.py`: lock CLI, state-independence, syntax, and shell behavior contracts.
- Modify `README.md`: document transient activation, persistent installation, and dynamic-name requirements.

---

### Task 1: Lock-free generator and static top-level completion

**Files:**
- Create: `lib/skillset/completions.py`
- Modify: `lib/skillset/cli.py:3-72`
- Modify: `tests/test_skillset.py:366-388`, near usage-error tests at `2127-2153`

**Interfaces:**
- Produces: `emit_completions(shell, output=None) -> None`; accepted keys are `bash`, `zsh`, and `fish`.
- Consumes: `sys.stdout` when `output` is omitted and the parsed `arguments.shell` value from `cli.main()`.
- Preserves: `parser() -> argparse.ArgumentParser`, `main() -> int`, and all existing lock paths.

Before editing, obtain explicit permission to change bead status, then run `br update agents-ph3 --status=in_progress`.

- [ ] **Step 1: Add RED CLI generation and state-independence tests**

Add `completions` to the exact command set in `test_help_includes_exact_supported_commands`. Add these tests nearby:

```python
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
    (self.root / "active").write_text("not a managed symlink", encoding="utf-8")
    before = self.filesystem_snapshot(self.home)

    result = self.run_cli("completions", "bash")

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stderr, "")
    self.assertIn("complete", result.stdout)
    self.assertEqual(self.filesystem_snapshot(self.home), before)
```

Extend `test_argparse_usage_errors_exit_two` with:

```python
("completions",),
("completions", "powershell"),
("completions", "bash", "extra"),
```

- [ ] **Step 2: Run the focused tests and verify RED failures**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_help_includes_exact_supported_commands \
  tests.test_skillset.SkillsetTests.test_completions_emit_deterministic_scripts_without_managed_state \
  tests.test_skillset.SkillsetTests.test_completions_bypass_malformed_managed_state_without_mutation \
  tests.test_skillset.SkillsetTests.test_argparse_usage_errors_exit_two
```

Expected: nonzero exit because `completions` is not in the parser. Existing usage-error cases must still behave normally.

- [ ] **Step 3: Create the emitter with valid static top-level scripts**

Create `lib/skillset/completions.py` with this initial complete content:

```python
"""Emit native shell completion scripts for skillset."""

import sys


COMMANDS = "init create use rename remove list current show doctor skills completions"

BASH = rf"""_skillset_completion() {{
    local current="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=()
    if (( COMP_CWORD == 1 )); then
        COMPREPLY=( $(compgen -W '-h --help {COMMANDS}' -- "$current") )
    fi
}}
complete -F _skillset_completion skillset
"""

ZSH = rf"""#compdef skillset
if (( ! $+functions[compdef] )); then
    autoload -Uz compinit && compinit
fi
_skillset() {{
    local -a commands
    commands=({COMMANDS})
    if (( CURRENT == 2 )); then
        _describe 'skillset command' commands
    fi
}}
compdef _skillset skillset
"""

FISH = """function __skillset_needs_command
    set -l tokens (commandline -opc)
    test (count $tokens) -eq 1
end
complete -c skillset -f
complete -c skillset -n __skillset_needs_command -s h -l help -d 'Show help'
complete -c skillset -n __skillset_needs_command -a 'init create use rename remove list current show doctor skills completions'
"""

SCRIPTS = {"bash": BASH, "zsh": ZSH, "fish": FISH}


def emit_completions(shell, output=None):
    output = sys.stdout if output is None else output
    output.write(SCRIPTS[shell])
```

The templates begin directly with shell content and already end with exactly one newline. Do not call `.strip()` during
emission because it obscures the byte contract.

- [ ] **Step 4: Add parser grammar and pre-lock dispatch**

Import the function in `lib/skillset/cli.py`:

```python
from .completions import emit_completions
```

Add the parser immediately before `skills_parser`:

```python
completions_parser = commands.add_parser(
    "completions", help="emit a shell completion script"
)
completions_parser.add_argument("shell", choices=("bash", "zsh", "fish"))
```

After `arguments = command_parser.parse_args()` and before `root = Path.home() / ".agents"`, add:

```python
if arguments.command == "completions":
    emit_completions(arguments.shell)
    return 0
```

Do not add `completions` to `inspection`: the early return must make lock bypass structurally obvious.

- [ ] **Step 5: Run focused GREEN tests and shell syntax checks**

Run the Step 2 command. Then add and run this test:

```python
def test_generated_completion_scripts_pass_available_shell_syntax_checks(self):
    checked = []
    for shell in ("bash", "zsh", "fish"):
        executable = shutil.which(shell)
        if executable is None:
            continue
        with self.subTest(shell=shell):
            generated = self.run_cli("completions", shell)
            checked.append(shell)
            parsed = subprocess.run(
                [executable, "-n"],
                input=generated.stdout,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(parsed.returncode, 0, parsed.stderr)
    self.assertIn("bash", checked)
```

Expected: both commands exit 0. On the design host Bash and Fish are checked; Zsh is skipped because it is not installed.

- [ ] **Step 6: Review the checkpoint and request permission before committing**

Run `jj diff -- lib/skillset/completions.py lib/skillset/cli.py tests/test_skillset.py`. Confirm generation is the only
new pre-lock path. If the user authorizes a commit, run:

```sh
jj commit -m "Add skillset completion script generator"
```

---

### Task 2: Contextual Bash completion

**Files:**
- Modify: `lib/skillset/completions.py` (`BASH` template)
- Modify: `tests/test_skillset.py` beside Task 1 completion tests

**Interfaces:**
- Consumes: Bash `COMP_WORDS`, `COMP_CWORD`, `compgen`, and public `skillset list` output.
- Produces: `_skillset_names`, `_skillset_positional_count`, `_skillset_completion`, and registration for `skillset`.
- Preserves: Task 1 generator bytes, exit behavior, and state-independent generation.

- [ ] **Step 1: Add a RED Bash behavior test**

```python
def test_bash_completion_is_contextual_and_uses_managed_names(self):
    bash = shutil.which("bash")
    self.assertIsNotNone(bash)
    self.initialize()
    self.make_set(self.root, "demo")
    generated = self.run_cli("completions", "bash")
    script = self.sandbox / "skillset.bash"
    script.write_text(generated.stdout, encoding="utf-8")
    environment = self.environment(extra={
        "PATH": f"{REPOSITORY_ROOT / 'bin'}:{os.environ.get('PATH', '')}"
    })
    probe = r'''source "$1"
COMP_WORDS=(skillset sh); COMP_CWORD=1; _skillset_completion
printf 'top:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset use d); COMP_CWORD=2; _skillset_completion
printf 'use:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset create --from=d); COMP_CWORD=2; _skillset_completion
printf 'from:%s\n' "${COMPREPLY[*]}"
COMP_WORDS=(skillset rename default n); COMP_CWORD=3; _skillset_completion
printf 'new:%s\n' "${#COMPREPLY[@]}"
COMP_WORDS=(skillset use -- -); COMP_CWORD=3; _skillset_completion
printf 'terminator:%s\n' "${#COMPREPLY[@]}"
COMP_WORDS=(skillset skills l); COMP_CWORD=2; _skillset_completion
printf 'skills:%s\n' "${#COMPREPLY[@]}"'''
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
            "from:--from=default --from=demo", "new:0",
            "terminator:0", "skills:0",
        ],
    )
```

- [ ] **Step 2: Run the Bash behavior test and verify RED failure**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_bash_completion_is_contextual_and_uses_managed_names
```

Expected: nonzero exit because the static Task 1 function has no name lookup or subcommand grammar.

- [ ] **Step 3: Replace the Bash template with the contextual implementation**

Replace `BASH` in `lib/skillset/completions.py` with:

```python
BASH = rf"""_skillset_names() {{
    local output line
    output="$(command skillset list 2>/dev/null)" || return 0
    while IFS= read -r line; do
        printf '%s\n' "${{line#\* }}"
    done <<< "$output"
}}

_skillset_positional_count() {{
    local index token skip=0 after_options=0 count=0
    for ((index = 2; index < COMP_CWORD; index++)); do
        token="${{COMP_WORDS[index]}}"
        if (( skip )); then ((skip--)); continue; fi
        if (( after_options )); then ((count++)); continue; fi
        case "$token" in
            --) after_options=1 ;;
            -f) skip=1 ;;
            --from)
                if [[ "${{COMP_WORDS[index+1]}}" == = ]]; then skip=2; else skip=1; fi
                ;;
            --from=*) ;;
            -h|--help|--use|--yes|-v|--verbose) ;;
            -*) ;;
            *) ((count++)) ;;
        esac
    done
    printf '%s' "$count"
}}

_skillset_after_option_terminator() {{
    local index
    for ((index = 2; index < COMP_CWORD; index++)); do
        [[ "${{COMP_WORDS[index]}}" == -- ]] && return 0
    done
    return 1
}}

_skillset_completion() {{
    local current="${{2-${{COMP_WORDS[COMP_CWORD]}}}}"
    local previous="${{COMP_WORDS[COMP_CWORD-1]}}"
    local subcommand position candidates value after_terminator=0
    COMPREPLY=()
    if (( COMP_CWORD == 1 )); then
        COMPREPLY=( $(compgen -W '-h --help {COMMANDS}' -- "$current") )
        return
    fi
    subcommand="${{COMP_WORDS[1]}}"
    position="$(_skillset_positional_count)"
    if _skillset_after_option_terminator; then after_terminator=1; fi
    case "$subcommand" in
        create)
            if (( ! after_terminator )) && [[ "$previous" == -f || "$previous" == --from ]]; then
                COMPREPLY=( $(compgen -W "$(_skillset_names)" -- "$current") )
                return
            fi
            if (( ! after_terminator && COMP_CWORD >= 2 )) &&
                    [[ "$previous" == = && "${{COMP_WORDS[COMP_CWORD-2]}}" == --from ]]; then
                COMPREPLY=( $(compgen -W "$(_skillset_names)" -- "$current") )
                return
            fi
            if (( ! after_terminator )) && [[ "$current" == --from=* ]]; then
                value="${{current#--from=}}"
                COMPREPLY=( $(compgen -W "$(_skillset_names)" -- "$value") )
                COMPREPLY=( "${{COMPREPLY[@]/#/--from=}}" )
                return
            fi
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help -f --from --use'; fi
            ;;
        use|remove|show)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            if (( ! after_terminator )) && [[ "$subcommand" == remove ]]; then candidates+=' --yes'; fi
            if (( position == 0 )); then candidates+=" $(_skillset_names)"; fi
            ;;
        rename)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            if (( position == 0 )); then candidates+=" $(_skillset_names)"; fi
            ;;
        list)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help -v --verbose'; fi
            ;;
        completions)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            if (( position == 0 )); then candidates+=' bash zsh fish'; fi
            ;;
        init|current|doctor)
            candidates=''
            if (( ! after_terminator )); then candidates='-h --help'; fi
            ;;
        skills) return ;;
        *) return ;;
    esac
    COMPREPLY=( $(compgen -W "$candidates" -- "$current") )
}}
complete -F _skillset_completion skillset
"""
```

Do not use `eval`. Candidate splitting is safe because managed names and static candidates contain no whitespace. Under
default Readline word breaks, Bash exposes `--from=d` as `--from`, `=`, and `d`; complete the final token while treating
the entire three-token sequence as one option argument for positional counting. For `--from=<TAB>`, prefer the completion
function's empty second argument over the `=` entry at `COMP_WORDS[COMP_CWORD]`.

- [ ] **Step 4: Run Bash behavior, syntax, and generator regression tests**

Run the Step 2 test, then:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_completions_emit_deterministic_scripts_without_managed_state \
  tests.test_skillset.SkillsetTests.test_generated_completion_scripts_pass_available_shell_syntax_checks
```

Expected: both commands exit 0; Bash returns exact contextual candidates and all installed shell parsers still accept
their generated script.

- [ ] **Step 5: Review the checkpoint and request permission before committing**

Run `jj diff -- lib/skillset/completions.py tests/test_skillset.py`. If the user authorizes a commit, run:

```sh
jj commit -m "Complete skillset commands in Bash"
```

---

### Task 3: Contextual Zsh and Fish completion

**Files:**
- Modify: `lib/skillset/completions.py` (`ZSH` and `FISH` templates)
- Modify: `tests/test_skillset.py` beside completion tests

**Interfaces:**
- Zsh produces `_skillset_names` and `_skillset`, registered with `compdef` after ensuring completion initialization.
- Fish produces `__skillset_names`, command/position predicates, and `complete` registrations with file completion off.
- Both consume public `skillset list` output only in contexts accepting an existing name.

- [ ] **Step 1: Add RED static grammar and Fish behavior tests**

```python
def test_completion_scripts_include_the_complete_wrapper_grammar(self):
    commands = (
        "init", "create", "use", "rename", "remove", "list",
        "current", "show", "doctor", "skills", "completions",
    )
    for shell in ("bash", "zsh", "fish"):
        with self.subTest(shell=shell):
            script = self.run_cli("completions", shell).stdout
            for command in commands:
                self.assertIn(command, script)
            options = (
                ("-l help", "-l from", "-l use", "-l yes", "-l verbose")
                if shell == "fish"
                else ("--help", "--from", "--use", "--yes", "--verbose")
            )
            for option in options:
                self.assertIn(option, script)
            self.assertIn("skillset list", script)
            self.assertIn("2>/dev/null", script)

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
    self.assertEqual(candidates("skillset rename default n"), [])
    self.assertEqual(candidates("skillset skills l"), [])
```

- [ ] **Step 2: Run the new tests and verify RED failures**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_completion_scripts_include_the_complete_wrapper_grammar \
  tests.test_skillset.SkillsetTests.test_fish_completion_is_contextual_and_uses_managed_names
```

Expected: nonzero exit because Task 1 Zsh/Fish scripts only complete top-level commands.

- [ ] **Step 3: Replace the Zsh template**

Replace `ZSH` in `lib/skillset/completions.py` with:

```python
ZSH = r"""#compdef skillset
if (( ! $+functions[compdef] )); then
    autoload -Uz compinit && compinit
fi

_skillset_names() {
    local output line
    output="$(command skillset list 2>/dev/null)" || return 0
    while IFS= read -r line; do
        print -r -- "${line#\* }"
    done <<< "$output"
}

_skillset() {
    local context state state_descr line
    typeset -A opt_args
    _arguments -S -C \
        -A "-*" \
        '(-h --help)'{-h,--help}'[show help]' \
        '1:command:->command' \
        '*::argument:->arguments' && return 0

    case "$state" in
        command)
            local -a commands
            commands=(
                'init:adopt existing global skills'
                'create:create a skillset'
                'use:activate a skillset'
                'rename:rename a skillset'
                'remove:remove an inactive skillset'
                'list:list managed skillsets'
                'current:print the active skillset name'
                'show:show skills in a skillset'
                'doctor:diagnose the managed layout'
                'skills:run managed upstream skills'
                'completions:emit a shell completion script'
            )
            _describe 'skillset command' commands
            ;;
        arguments)
            case "${words[1]}" in
                init)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1:name:' && return 0
                    ;;
                create)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '(-f --from)'{-f,--from=}'[clone from an existing skillset]:source skillset:->skillsets' \
                        '--use[activate the created skillset]' \
                        '1:name:' && return 0
                    ;;
                use)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1:name:->skillsets' && return 0
                    ;;
                rename)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '1:old name:->skillsets' '2:new name:' && return 0
                    ;;
                remove)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '--yes[skip confirmation]' '1:name:->skillsets' && return 0
                    ;;
                list)
                    _arguments -S \
                        '(-h --help)'{-h,--help}'[show help]' \
                        '(-v --verbose)'{-v,--verbose}'[show skill inventory]' && return 0
                    ;;
                current|doctor)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' && return 0
                    ;;
                show)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1::name:->skillsets' && return 0
                    ;;
                completions)
                    _arguments -S '(-h --help)'{-h,--help}'[show help]' '1:shell:(bash zsh fish)' && return 0
                    ;;
                skills) return 0 ;;
            esac
            if [[ "$state" == skillsets ]]; then
                local -a names
                names=("${(@f)$(_skillset_names)}")
                (( ${#names} )) && _describe 'skillset' names
            fi
            ;;
    esac
}

if [[ "${zsh_eval_context[-1]}" == loadautofunc ]]; then
    _skillset "$@"
else
    compdef _skillset skillset
fi
"""
```

Keep delegated `skills` arguments out of nested `_arguments`; otherwise Zsh may fall back to file candidates.
The outer `*::` action rewrites `words` to normal arguments, so nested dispatch uses `words[1]`. `-S` makes `--` an
option terminator, and the `--from=` optspec accepts both `--from VALUE` and `--from=VALUE`. A file discovered through
`fpath` is executing in `loadautofunc` context on its first call and must invoke the newly defined implementation
immediately; a directly sourced script registers that implementation for later calls. `-A "-*"` prevents the outer
parser from offering wrapper options after a subcommand, and each nested parser returns immediately after adding matches.

- [ ] **Step 4: Replace the Fish template**

Replace `FISH` with:

```python
FISH = """function __skillset_names
    set -l output (command skillset list 2>/dev/null)
    set -l list_status $status
    test $list_status -eq 0; or return 0
    test (count $output) -gt 0; or return 0
    string replace -r '^\\* ' '' $output
end

function __skillset_needs_command
    set -l tokens (commandline -xpc)
    test (count $tokens) -eq 1
end

function __skillset_using_command
    set -l tokens (commandline -xpc)
    test (count $tokens) -ge 2; and test $tokens[2] = $argv[1]
end

function __skillset_positional_count
    set -l tokens (commandline -xpc)
    set -e tokens[1..2]
    set -l count 0
    set -l skip false
    set -l after_options false
    for token in $tokens
        if test $skip = true
            set skip false
            continue
        end
        if test $after_options = true
            set count (math $count + 1)
            continue
        end
        switch $token
            case --
                set after_options true
            case -f --from
                set skip true
            case '--from=*' -h --help --use --yes -v --verbose '-*'
            case '*'
                set count (math $count + 1)
        end
    end
    echo $count
end

function __skillset_at_position
    test (__skillset_positional_count) -eq $argv[1]
end

complete -c skillset -f
complete -c skillset -n __skillset_needs_command -s h -l help -d 'Show help'
complete -c skillset -n __skillset_needs_command -a init -d 'Adopt existing global skills'
complete -c skillset -n __skillset_needs_command -a create -d 'Create a skillset'
complete -c skillset -n __skillset_needs_command -a use -d 'Activate a skillset'
complete -c skillset -n __skillset_needs_command -a rename -d 'Rename a skillset'
complete -c skillset -n __skillset_needs_command -a remove -d 'Remove an inactive skillset'
complete -c skillset -n __skillset_needs_command -a list -d 'List managed skillsets'
complete -c skillset -n __skillset_needs_command -a current -d 'Print the active skillset name'
complete -c skillset -n __skillset_needs_command -a show -d 'Show skills in a skillset'
complete -c skillset -n __skillset_needs_command -a doctor -d 'Diagnose the managed layout'
complete -c skillset -n __skillset_needs_command -a skills -d 'Run managed upstream skills'
complete -c skillset -n __skillset_needs_command -a completions -d 'Emit a shell completion script'

for subcommand in init create use rename remove list current show doctor completions
    complete -c skillset -n "__skillset_using_command $subcommand" -s h -l help -d 'Show help'
end
complete -c skillset -n '__skillset_using_command create' -s f -l from -x -a '(__skillset_names)' -d 'Clone from a skillset'
complete -c skillset -n '__skillset_using_command create' -l use -d 'Activate the created skillset'
complete -c skillset -n '__skillset_using_command use; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command rename; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command remove; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command remove' -l yes -d 'Skip confirmation'
complete -c skillset -n '__skillset_using_command list' -s v -l verbose -d 'Show skill inventory'
complete -c skillset -n '__skillset_using_command show; and __skillset_at_position 0' -a '(__skillset_names)'
complete -c skillset -n '__skillset_using_command completions; and __skillset_at_position 0' -a 'bash zsh fish'
"""
```

Do not include `skills` in the Fish help loop: that parser intentionally has `add_help=False`, and all following tokens
belong to the upstream CLI. Every dynamic-name helper buffers `skillset list` output and checks its status before emitting
names, so plausible partial stdout from a failed lookup cannot become a candidate.

- [ ] **Step 5: Run contextual, grammar, and syntax tests**

Run the Step 2 command, then:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_zsh_completion_uses_stateful_nested_parser_contract \
  tests.test_skillset.SkillsetTests.test_generated_zsh_completion_script_passes_syntax_check \
  tests.test_skillset.SkillsetTests.test_bash_completion_is_contextual_and_uses_managed_names \
  tests.test_skillset.SkillsetTests.test_generated_completion_scripts_pass_available_shell_syntax_checks \
  tests.test_skillset.SkillsetTests.test_completions_bypass_malformed_managed_state_without_mutation
```

Expected: both commands exit 0. Fish behavior is exercised when installed; Zsh syntax is exercised when installed and
is otherwise covered by static grammar assertions.

- [ ] **Step 6: Review the checkpoint and request permission before committing**

Run `jj diff -- lib/skillset/completions.py tests/test_skillset.py`. Confirm no generated script evaluates candidate
output and no dynamic lookup appears in generation-time Python. If authorized, run:

```sh
jj commit -m "Complete skillset commands in Zsh and Fish"
```

---

### Task 4: User documentation and full verification

**Files:**
- Modify: `README.md` after “Requirements and PATH”
- Verify: `lib/skillset/completions.py`, `lib/skillset/cli.py`, `tests/test_skillset.py`

**Interfaces:**
- Documents: transient sourcing commands and shell-managed persistent installation.
- Verifies: the public CLI, generated shell syntax, dynamic candidates, and unchanged existing behavior.

- [ ] **Step 1: Add README activation and persistence guidance**

Insert this section after the PATH setup:

````markdown
## Shell completions

Load completions for the current shell session:

```sh
# Bash
source <(skillset completions bash)

# Zsh
source <(skillset completions zsh)

# Fish
skillset completions fish | source
```

For persistent completion, redirect the generated script to a file in your shell's normal completion directory and
restart the shell. The destination depends on the shell and distribution.

Script generation does not require an initialized or healthy managed layout. Command and option completion is always
available after loading the script; existing skillset-name completion calls `skillset list` and therefore requires a
healthy managed layout at completion time. Arguments following `skillset skills` are left to the upstream CLI.
````

Use a four-backtick outer fence around the Markdown excerpt while editing the plan if needed; the README itself retains
the normal triple-backtick shell fence shown inside the excerpt.

- [ ] **Step 2: Run all completion-focused tests**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_help_includes_exact_supported_commands \
  tests.test_skillset.SkillsetTests.test_completions_emit_deterministic_scripts_without_managed_state \
  tests.test_skillset.SkillsetTests.test_completions_bypass_malformed_managed_state_without_mutation \
  tests.test_skillset.SkillsetTests.test_generated_completion_scripts_pass_available_shell_syntax_checks \
  tests.test_skillset.SkillsetTests.test_completion_scripts_include_the_complete_wrapper_grammar \
  tests.test_skillset.SkillsetTests.test_bash_completion_is_contextual_and_uses_managed_names \
  tests.test_skillset.SkillsetTests.test_fish_completion_is_contextual_and_uses_managed_names \
  tests.test_skillset.SkillsetTests.test_argparse_usage_errors_exit_two
```

Expected: exit 0 with eight passing tests on the design host. A missing Fish produces one explicit skip; missing Zsh only
omits its syntax subtest while static Zsh assertions still run.

- [ ] **Step 3: Run the complete regression suite**

Run:

```sh
python3 -m unittest discover -s tests -v
```

Expected: exit 0 with all tests passing, aside from declared optional-shell skips. Investigate any failure before
claiming completion; do not weaken unrelated tests.

- [ ] **Step 4: Inspect final state and planning-term leakage**

Run:

```sh
grep -RniE 'phase|milestone|bead|TODO|TBD' lib tests README.md || true
jj status
jj diff --stat
jj diff --check
br show agents-ph3
```

Expected: no planning terms in implementation-facing files, no whitespace errors, bead `agents-ph3` still open unless
the user authorized status changes, and only the planned files plus approved spec/plan and tracker metadata differ.

- [ ] **Step 5: Request permission for the final commit and bead closure**

Report exact test commands, exit statuses, pass/skip counts, and the diff summary. If the user authorizes both actions,
run:

```sh
jj commit -m "Document skillset shell completions"
br close agents-ph3 --reason="Completed"
br sync --flush-only
```

If implementation was intentionally kept in one uncommitted change rather than checkpoint commits, use one final commit
message instead: `Add skillset shell completions`. Do not advance a bookmark or push without separate explicit approval.
