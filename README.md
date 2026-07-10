# Named Agent Skillsets

`skillset` manages multiple named global agent skill collections under
`~/.agents/skillsets` and activates one collection through stable relative
symlinks. The current Linux-only core provides lifecycle and inspection
commands plus managed delegation to the upstream `skills` CLI.

## Requirements and PATH

The CLI requires Linux and Python 3 and uses only the Python standard library.
Add its directory to your shell startup file, then start a new shell:

```sh
export PATH="$HOME/.agents/bin:$PATH"
```

## Initialize the current installation

Choose a lowercase name for the current global collection:

```sh
skillset init default
```

This adopts existing real `~/.agents/skills` and
`~/.agents/.skill-lock.json` entries. Missing entries are created. Existing
symlinks or a partial managed layout are refused rather than guessed at.

## Create skillsets

Create an empty inactive set:

```sh
skillset create experiment
```

Or clone both the complete skills tree and lock metadata from another set:

```sh
skillset create experiment --from default
```

Names use lowercase letters, digits, underscores, and hyphens, and must start
with a letter or digit.

## Activate a skillset

```sh
skillset use experiment
```

Activation atomically retargets `~/.agents/active`; the stable `skills` and
`.skill-lock.json` aliases remain unchanged.

## Rename skillsets

Rename an inactive set without changing the active aliases:

```sh
skillset rename experiment trial
```

The active set can be renamed with the same command:

```sh
skillset rename default baseline
```

An active rename moves the complete set first and then atomically retargets
`~/.agents/active`; the stable root aliases remain unchanged. Rename refuses
any existing destination, including files and symlinks, without overwriting it.
If active retargeting fails before it commits, the directory rename is rolled
back. If rollback cannot restore a valid layout, the error names the old, new,
and active paths and identifies the remaining data location. Preserve that copy
and inspect the reported state before either moving the set back or retargeting
`active`; run `skillset doctor` when it is available.

## Remove skillsets

Remove an inactive set with an interactive confirmation:

```text
$ skillset remove trial
Remove skillset 'trial'? [y/N] yes
```

Only `y` or `yes`, ignoring case and surrounding whitespace, confirms removal.
Use `--yes` for noninteractive operation:

```sh
skillset remove trial --yes
```

The active set is always refused, even with `--yes`. Activate another set with
`skillset use` before removing it.

## Inspect skillsets

List sets in sorted order. The active set is the only one prefixed with `* `:

```text
$ skillset list
* default
experiment
```

Verbose output with either `-v` or `--verbose` adds a tab followed by sorted
valid declared skill names, or `(no skills)` when none are valid:

```text
$ skillset list --verbose
* default	alpha, zeta
experiment	(no skills)
```

Print only the active name and its terminating newline for use in scripts:

```text
$ skillset current
default
```

Show one set's direct skill directories, sorted by the displayed name:

```text
$ skillset show default
alpha — First skill
broken-directory — [invalid: missing description]
```

`show` reads UTF-8 `SKILL.md` files whose first line is exactly `---` and that
have a later exact `---` closing line. Before that close, top-level `name` and
`description` must each appear exactly once and be nonempty. The focused,
dependency-free reader supports plain scalars, YAML-style single quotes with
doubled apostrophes, JSON-compatible double-quoted escapes, and exact `|` or
`>` markers followed by indented block content. Plain and quoted values may
continue on indented physical lines, and trailing comments are ignored outside
quotes. It ignores extra keys and the body, and collapses whitespace in both
displayed values.

Malformed, non-UTF-8, or invalid decoded-Unicode candidates remain visible as
`<directory> — [invalid: <reason>]`; verbose `list` omits them. Direct regular
files are ignored. Direct skill-directory symlinks and `SKILL.md` symlinks are
never followed.

## Install and maintain skills

After activating the intended set, run upstream commands through the wrapper:

```sh
skillset skills add SOURCE
skillset skills list
skillset skills remove SKILL
skillset skills update
```

For `add`, `list`/`ls`, `remove`/`rm`, and `update`, the wrapper injects
`--global` unless exact `-g` or `--global` is already present before an option
terminator. It inserts the flag before `--`, or appends it when no terminator is
present. Exact `-p` and `--project` options are rejected for those commands
because managed skillsets contain global state; tokens after `--` remain
literals. Scope-free `find`, `use`, and upstream `init` commands, as well as an
invocation with no upstream arguments, pass through unchanged:

```sh
skillset skills find formatter
skillset skills use SKILL
```

Unknown upstream commands also pass through unchanged, but the wrapper warns
on stderr that global scope was not injected. It does not reinterpret other
upstream arguments or output. The delegated process inherits terminal streams,
signals, and exit status; only its copied environment has `XDG_STATE_HOME`
removed so lock metadata resolves through the active managed alias.

All `skillset` management, inspection, and delegated operations share one
advisory lock. Inspection waits for that lock, validates the complete managed
layout, and remains read-only. Delegation holds the lock for the complete
`npx skills` process lifetime, so wrapper operations safely wait for one
another. Prefer `skillset skills ...` after initialization: direct `npx skills`
commands cannot honor this lock and must not run concurrently with `skillset`
operations.

## Recovery

Operations refuse invalid layouts and stale staging paths without deleting
them. When an error names recovery paths, inspect those paths before changing
anything and preserve the only remaining copy of any skill data. Automated
diagnostics and repair guidance will be added with the later `doctor` command.