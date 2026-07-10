# Named Agent Skillsets

`skillset` manages multiple named global agent skill collections under
`~/.agents/skillsets` and activates one collection through stable relative
symlinks. The Linux-only CLI provides lifecycle, inspection, and diagnostic
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

Create and activate an empty set in one command:

```sh
skillset create --use experiment
```

Clone and activate in one command:

```sh
skillset create --use --from default experiment
```

Options may appear before or after `NAME`. If creation succeeds but activation
fails before replacement, the new set remains and the previous set stays active;
inspect it and retry `skillset use NAME`.

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
`active`; then run `skillset doctor`.

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

Show the active set's direct skill directories, sorted by the displayed name:

```text
$ skillset show
SKILL            | DESCRIPTION
-----------------|-------------------------------
alpha            | First skill
broken-directory | [invalid: missing description]
```

`NAME` is optional for `skillset show [NAME]`: omitting it inspects the active
skillset, while an explicit name inspects that set whether it is active or
inactive. Non-empty sets use the headered, aligned `SKILL | DESCRIPTION` table
shown above. An empty set prints `No skills installed.` without table headers.

When stdout is a TTY, `NO_COLOR` is absent, and `TERM` is not `dumb`, `show`
makes both header cells bold and valid skill names cyan. It colors
`[invalid: missing description]` yellow and every other invalid description red,
makes every row's `|` delimiter and the complete separator dim, and also dims the
empty-set message. All non-TTY output, including pipes and redirects, is plain
text; `NO_COLOR` and `TERM=dumb` also suppress ANSI styling.

`show` reads UTF-8 `SKILL.md` files whose first line is exactly `---` and that
have a later exact `---` closing line. Before that close, top-level `name` and
`description` must each appear exactly once and be nonempty. The focused,
dependency-free reader supports plain scalars, YAML-style single quotes with
doubled apostrophes, JSON-compatible double-quoted escapes, and exact `|` or
`>` markers followed by indented block content. Plain and quoted values may
continue on indented physical lines, and trailing comments are ignored outside
quotes. It ignores extra keys and the body, and collapses whitespace in both
displayed values.

Malformed, non-UTF-8, or invalid decoded-Unicode candidates remain visible in
the table as `<directory> | [invalid: <reason>]`; verbose `list` omits them.
Direct regular files are ignored. Direct skill-directory symlinks and
`SKILL.md` symlinks are never followed. Declared names and descriptions preserve
ordinary printable Unicode, while terminal controls, invisible format controls,
and line/paragraph separators are rendered as deterministic `\xNN`, `\uNNNN`,
or `\UNNNNNNNN` escapes. Wrapper-created tabs, table delimiters, and line
endings remain unchanged.

## Diagnose the managed layout

Run the read-only diagnostic command after initialization, when another command
reports an invalid layout, or before attempting manual recovery:

```sh
skillset doctor
```

`doctor` first takes the stable advisory lock on the existing HOME directory. It
then inspects `.skillset.lock` without following it and, when it is a real regular
file, holds that lock for the full inspection. A missing `.agents` root or a
missing, symlinked, or nonregular managed lock is reported alongside missing
aliases, `active`, and `skillsets`; neither path is created. `doctor` never
creates, removes, rewrites, retargets, or repairs state, and does not stop at the
first invalid component. It checks all three canonical aliases, the active target
grammar and existence, direct skillset directory names and shapes, stale
use/create staging markers, readable version-3 lockfiles, and each direct skill
directory's `SKILL.md` metadata. Set directories, skill directories, and
`SKILL.md` files must be real entries; diagnostic inspection never follows their
symlinks.

Every finding is written to stderr on one line. Structural, alias, lockfile,
metadata, symlink, and staging problems are `skillset: error:` findings. A lock
entry without a corresponding real direct skill directory, or an installed
directory absent from the lockfile, is a `skillset: warning:` finding. Direct
regular files under `skills` are not installed skill directories and are
otherwise ignored. Finding text uses the same visible escaping for controls and
line separators, so each finding remains one physical line. Errors are printed
before warnings. Any error produces exit status 1; warnings alone and a healthy
layout produce status 0. A healthy run may print nothing.

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

All `skillset` management, inspection, diagnostic, and delegated operations first
take a stable, non-creating advisory lock on the existing HOME directory. Routine
operations then take `~/.agents/.skillset.lock`, always in that order, and retain
its existing on-disk compatibility. Routine inspection validates the complete
managed layout and remains read-only; `doctor` aggregates invalid and partial
state and acquires the managed lock only when it is a safe regular file.
Delegation preserves both locks for the complete `npx skills` process lifetime,
so wrapper operations safely wait for one another. After initialization, always
prefer `skillset skills ...` for global installation and maintenance. Direct
`npx skills` commands cannot honor these locks and must not run concurrently with
any `skillset` operation.

## Recovery

Operations refuse invalid layouts and stale staging paths without deleting
them. When an error names recovery paths:

1. Preserve the only remaining copy of every skill directory and lockfile.
2. Run `skillset doctor` and review every error and warning before changing
   anything.
3. Inspect the concrete original, staged, old, new, and active paths named by
   the failed operation.
4. Restore a missing original only from its staged counterpart, or move a set
   back/retarget `active` only after confirming which path contains the data.
5. Run `skillset doctor` again after manual recovery.

`doctor` is deliberately strict and non-repairing: it never deletes stale
markers, rewrites lock metadata, changes aliases, or chooses between competing
copies. Resolve findings manually only after preserving the data they identify.