# Named Agent Skillsets

`skillset` manages multiple named global agent skill collections under
`~/.agents/skillsets` and activates one collection through stable relative
symlinks. The current Linux-only core provides `init`, `create`, `use`, and
managed delegation to the upstream `skills` CLI.

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

All `skillset` management and delegated operations share one advisory lock.
Delegation holds it for the complete `npx skills` process lifetime, so wrapper
operations safely wait for one another. Prefer `skillset skills ...` after
initialization: direct `npx skills` commands cannot honor this lock and must not
run concurrently with `skillset` operations.

## Recovery

Operations refuse invalid layouts and stale staging paths without deleting
them. When an error names recovery paths, inspect those paths before changing
anything and preserve the only remaining copy of any skill data. Automated
diagnostics and repair guidance will be added with the later `doctor` command.