# `skillset` Shell Completions Design

## Purpose

Add `skillset completions SHELL`, which writes a sourceable completion script for Bash, Zsh, or Fish. The installed
completion provides wrapper command and option candidates plus context-sensitive existing skillset names. Arguments
delegated through `skillset skills` remain opaque.

## Repository context

- `bin/skillset` invokes the dependency-free Python package under `lib/skillset`.
- `lib/skillset/cli.py` owns the `argparse` grammar, command dispatch, and lock acquisition.
- Routine commands currently acquire a stable HOME lock and, except for `doctor`, the managed operation lock.
- `skillset list` prints sorted skillset names, prefixing only the active name with `* `; captured output is plain text.
- Black-box CLI coverage is in `tests/test_skillset.py`.
- The README documents a Linux-only, Python-standard-library-only installation.
- At design start, Jujutsu reported a clean working copy at an empty commit after `Improve verbose skillset listing
  output`. Bead `agents-ph3` tracks implementation; creating it changed tracker state after design began.

No new runtime dependency is required. Final implementation review consulted the official Zsh 5.9.1 completion-system
documentation at <https://zsh.sourceforge.io/Doc/Release/Completion-System.html>. It confirms that a `*::` action
rewrites `words` and `CURRENT` to normal arguments, `_arguments -S` treats `--` as an option terminator, and a
`--from=` option specification accepts both separated and equals-sign arguments. It also specifies `-A "-*"` for
stopping option completion after the first normal argument and requires a zero return when matches were added. The
official autoload documentation at
<https://zsh.sourceforge.io/Doc/Release/Functions.html> establishes that a multi-statement completion file is executed
on its first autoload call. The generated script therefore detects a final `loadautofunc` evaluation context and invokes
its implementation immediately; direct sourcing instead registers that implementation with `compdef`.

The GNU Bash programmable-completion documentation at
<https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion.html> defines `COMP_WORDS`, `COMP_CWORD`,
and `COMP_WORDBREAKS`. A final-review interactive PTY probe with the host's default word breaks observed
`skillset create --from=d` as `skillset`, `create`, `--from`, `=`, `d`, with `COMP_CWORD=4`. Bash completion handles
both that real Readline shape and the unsplit shape used by direct completion-function callers. At
`skillset create --from=<TAB>`, the array ends in `=`, while the completion function's second argument is the required
empty current word; the implementation prefers that argument when Bash supplies it.

The current Fish `commandline` documentation at <https://fishshell.com/docs/current/cmds/commandline.html> deprecates
raw tokenization through `-o` and identifies `commandline -xpc` as the completion-oriented form for completed tokens.

## Public command contract

The accepted invocations are exactly:

```text
skillset completions bash
skillset completions zsh
skillset completions fish
```

Each successful invocation exits 0, writes one complete sourceable script to stdout, writes nothing to stderr, and ends
with exactly one newline. Script generation is deterministic and independent of HOME contents.

`SHELL` is a required `argparse` choice. A missing shell, unsupported shell, option-like unknown value, or extra argument
is a normal usage error: usage is written to stderr and the process exits 2. `skillset completions --help` follows normal
subparser help behavior.

## State and locking contract

Completion generation is dispatched before resolving the managed root or acquiring either lock. It succeeds in a
pristine HOME and when `.agents` is incomplete, malformed, or otherwise unavailable. It never creates, validates,
repairs, or mutates managed state.

The generated scripts query state only while interactively completing an argument that accepts an existing skillset.
They invoke the `skillset` found through `PATH`, run `skillset list` with stderr suppressed, remove an optional leading
`* ` active marker, and pass the resulting names to native shell completion APIs. A failed lookup produces no dynamic
candidates, even if the failed process wrote plausible partial stdout: each helper buffers the complete output and checks
the exit status before parsing any line. Because lookup uses the public command, it retains normal validation and locking
and may wait briefly behind an active operation.

## Completion grammar

All scripts register completion for the command name `skillset`, without embedding the repository path. They provide
these candidates:

- Top level: every public subcommand plus `-h` and `--help`.
- `init`: help; `NAME` remains user-entered.
- `create`: `-f`, `--from`, `--use`, and help. The value of `-f`/`--from` completes existing names; the new `NAME` does
  not. Options may occur before or after `NAME`, matching `argparse`. Separated and `--from=VALUE` forms are recognized.
- `use`: existing names and help.
- `rename`: existing names for `OLD` and help; `NEW` remains user-entered.
- `remove`: existing names, `--yes`, and help.
- `list`: `-v`, `--verbose`, and help.
- `current`: help only.
- `show`: existing names for optional `NAME` and help.
- `doctor`: help only.
- `completions`: `bash`, `zsh`, `fish`, and help.
- `skills`: no wrapper-provided candidates after the subcommand.

The scripts honor the option terminator where relevant and filter candidates by the current token. They do not infer
upstream `skills` grammar, complete skill names, inspect skill metadata, complete files, or alter command execution.

## Architecture and responsibilities

Create `lib/skillset/completions.py`. It owns immutable Bash, Zsh, and Fish script templates and an emission function
that selects a script from an explicit shell-to-template mapping and writes it to an output stream. Keeping shell syntax
out of `cli.py` avoids turning parser orchestration into a quoting-heavy mixed-language module.

`lib/skillset/cli.py` adds a `completions` subparser with the required shell choices. Immediately after parsing,
`main()` dispatches this command and returns its status before calculating `root`, classifying inspection commands, or
entering `stable_home_lock`. Existing command dispatch and lock semantics remain unchanged.

The shell templates independently encode the approved public grammar using native facilities:

- Bash registers a completion function with `complete`, reads Bash's explicit current-word argument, normalizes the split
  `--from`, `=`, `VALUE` shape, and writes candidates to `COMPREPLY`.
- Zsh defines an implementation function. Direct sourcing registers it with `compdef`; `fpath` autoloading invokes it on
  the first call when `zsh_eval_context` ends in `loadautofunc`. Its outer parser stops wrapper options after the
  subcommand, and nested parsers return immediately after successfully adding matches.
- Fish declares context-sensitive candidates with `complete` and tokenizes completed arguments with `commandline -xpc`.

Dynamic lines are treated as candidate data, not evaluated as shell code. Managed names already use the restricted
lowercase name grammar, and `skillset list` validates and sanitizes its output before a script consumes it.

## Documentation

Add a README section describing transient activation:

```text
Bash: source <(skillset completions bash)
Zsh:  source <(skillset completions zsh)
Fish: skillset completions fish | source
```

Also explain that users may redirect the generated script into their shell's normal completion directory for persistent
installation. Do not prescribe one global destination because conventions vary by shell and distribution. Clarify that
Zsh `fpath` installation requires an underscore-prefixed filename such as `_skillset`. State that dynamic skillset-name
completion requires a healthy managed layout, while script generation does not.

## Verification strategy

Update `tests/test_skillset.py` to establish:

1. Top-level help lists `completions` in the exact supported command set.
2. Every supported shell exits 0, emits a nonempty deterministic script with exactly one final newline, and has empty
   stderr.
3. Generation succeeds without initialization and leaves a pristine HOME byte-for-byte unchanged.
4. Generation succeeds with deliberately malformed managed state and does not alter it.
5. Missing, unsupported, and extra shell arguments exit 2.
6. Every script represents all public subcommands, relevant options, supported shell names, dynamic-name lookup, stderr
   suppression, failed-lookup stdout rejection, and opaque delegated arguments.
7. Generated output passes `bash -n`, `zsh -n`, or `fish -n` when that executable is installed. An unavailable Zsh
   executable is reported as an explicit skipped test. Static Zsh contracts lock rewritten-word dispatch, `--from=`
   support, option-terminator parsing, post-subcommand option stopping, nested success propagation, opaque delegation,
   and the dual source/autoload bootstrap.
8. Bash behavior is tested in a subprocess with unsplit arguments, the real default Readline split around `=`, and the
   empty current-word argument supplied for `--from=<TAB>`.
   Fish uses its noninteractive completion API. When Zsh is installed, a temporary `_skillset` file is discovered by
   `compinit` and its first autoload call must execute the completion implementation.
9. Existing lock, read-only inspection, delegation, help, workflow, and usage-error tests continue to pass.

Write focused failing tests before production code. Run focused completion tests while iterating, then run:

```text
python3 -m unittest discover -s tests -v
```

Final verification reports commands, exit statuses, test counts, skipped optional-shell checks, and the final Jujutsu
diff summary.

## Rejected alternatives and trade-offs

- A hidden `skillset _complete` protocol would centralize candidate decisions but add a private CLI surface and a Python
  process to most completion steps.
- A completion framework or CLI rewrite could generate some scripts automatically but adds installation and runtime
  complexity to a dependency-free tool.
- Reading `~/.agents/skillsets` directly from each shell avoids lock waits but duplicates managed-layout and name rules,
  bypasses validation, and couples scripts to storage details.
- Completing delegated upstream commands would couple this wrapper to a separately versioned CLI and is explicitly out
  of scope.
- Deriving scripts automatically from private `argparse` internals is fragile and does not express dynamic shell-native
  behavior cleanly. Handwritten grammar duplication is accepted and guarded by contract tests.

## Implementation checklist

1. Claim bead `agents-ph3` and add focused red CLI and script-contract tests.
2. Add shell subprocess syntax and behavior coverage with explicit optional-shell skips.
3. Add the completion module and pre-lock parser dispatch.
4. Update README activation and persistence guidance.
5. Run focused tests, then the full suite, and inspect the final Jujutsu diff.
6. Keep unrelated working-copy changes untouched and report them separately.
