# Named Agent Skillsets

`skillset` manages multiple named global agent skill collections under
`~/.agents/skillsets` and activates one collection through stable relative
symlinks. The current Linux-only core provides `init`, `create`, and `use`.

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

## Temporary upstream usage

Until managed upstream delegation is added, run global `npx skills` commands
with `XDG_STATE_HOME` removed so lock metadata stays under `~/.agents`:

```sh
env -u XDG_STATE_HOME npx skills add SOURCE -g
```

Run such commands only after activating the intended set. Avoid concurrent
direct `npx skills` and `skillset` operations because direct upstream commands
do not participate in `skillset`'s advisory lock.

## Recovery

Operations refuse invalid layouts and stale staging paths without deleting
them. When an error names recovery paths, inspect those paths before changing
anything and preserve the only remaining copy of any skill data. Automated
diagnostics and repair guidance will be added with the later `doctor` command.