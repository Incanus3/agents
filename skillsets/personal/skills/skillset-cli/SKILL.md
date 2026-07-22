---
name: skillset-cli
description: >-
  Operate the Linux `skillset` CLI that manages named global agent skill
  collections under `~/.agents`, delegates upstream `skills` commands, and
  exposes collections to Codex and Claude Code. Use when initializing,
  inspecting, cloning, activating, renaming, removing, diagnosing, or repairing
  skillsets; installing or updating skills in a managed collection; maintaining
  a manual collection; configuring external skillset storage; managing global
  or project-local Codex or Claude Code discovery; or generating shell
  completions.
---

# Skillset CLI

Treat `skillset` as the owner of global skill state after initialization. Invoke
the installed `skillset` command directly.

## Keep the State Model Straight

Distinguish four independent concepts:

- **Active skillset:** the one exposed through `~/.agents/skills` and used by
  `skillset skills ...`. Exactly one is active.
- **Codex-enabled skillset:** a collection linked below global
  `~/.codex/skills` or the current project's `.codex/skills`. Multiple
  collections may be enabled; enablement does not activate a set.
- **Claude Code-enabled skillset:** a registration below `.claude/.skillsets`
  plus one flat link per direct source skill below `.claude/skills`. Multiple
  collections may be enabled when their skill-directory basenames do not
  collide; enablement does not activate a set.
- **Collection mode:** managed sets have `.skill-lock.json` and use delegated
  upstream maintenance; manual sets have `.skillset-manual` and are edited
  directly.

Treat mode markers as mutually exclusive: a lockfile without a manual marker is
managed, and a manual marker without a lockfile is manual. Both entries or
neither entry make the set invalid. Do not add or remove either entry to guess
the intended mode; `doctor --fix` can create a managed empty lockfile only when
the real `skills/` directory is empty.

Do not infer tool enablement from the active marker or activation from a Codex
or Claude Code listing.

## Inspect Before Mutating

Use the smallest relevant read-only commands:

```text
skillset list
skillset list --verbose
skillset current
skillset show
skillset show <name>
skillset codex list
skillset codex list --global
skillset codex list --local
skillset claude list
skillset claude list --global
skillset claude list --local
skillset doctor
```

Run local-scope integration commands from the exact intended directory; the CLI
does not resolve a repository root. If routine inspection reports an invalid
layout, run `skillset doctor`; do not initialize, rewrite aliases, remove
staging paths, or invent lock metadata.

## Manage the Lifecycle

Initialize once, optionally adopting existing real `~/.agents/skills` and
`~/.agents/.skill-lock.json` entries:

```text
skillset init <name>
```

Create, clone, activate, rename, and remove:

```text
skillset create <name>
skillset create --from <source> <name>
skillset create --manual <name>
skillset create --use <name>
skillset create --use --from <source> <name>
skillset use <name>
skillset rename <old> <new>
skillset remove <name>
skillset remove <name> --yes
```

Use names that start with a lowercase letter or digit and contain only lowercase
letters, digits, `_`, or `-`. Cloning preserves the source's managed/manual
mode. Remove only an inactive set; use interactive removal unless the user
explicitly requested noninteractive confirmation. Before rename or removal,
disable any global Codex link or Claude Code registration. Also disable known
project-local Codex links and Claude Code registrations from their project
directories because the CLI cannot discover them in other projects.

If `create --use` creates the set but activation fails, keep the new set,
inspect it, and retry `skillset use <name>` after resolving the reported cause.

## Maintain Skills

Activate the intended managed set, then delegate upstream operations through the
wrapper:

```text
skillset skills add <source>
skillset skills list
skillset skills remove <skill>
skillset skills update
skillset skills find <query>
skillset skills use <skill>
```

Never substitute direct concurrent `npx skills` operations after initialization.
The wrapper serializes access, removes `XDG_STATE_HOME` from the child, rejects
project scope for lock-aware commands, and injects `--global` for `add`,
`list`/`ls`, `remove`/`rm`, and `update`. It otherwise preserves upstream
arguments, streams, signals, and exit status.

For a manual active set, do not run the lock-aware delegated commands above.
Edit the set's real `skills/` tree directly, then verify with
`skillset show <name>` and `skillset doctor`. Scope-free upstream commands such
as `find` and `use` remain available through the wrapper.

## Control Codex Discovery

`enable` and `disable` default to global scope. An unscoped `list` combines
global and current-project entries; use `--global` or `--local` to filter it:

```text
skillset codex enable <name>
skillset codex disable <name>
skillset codex enable <name> --local
skillset codex disable <name> --local
skillset codex list --verbose
skillset codex list --local --verbose
```

Enable is idempotent only for the exact canonical link. Never replace an
unrelated entry beneath `.codex/skills`; investigate the collision. Disable
removes only the expected canonical link.

## Control Claude Code Discovery

`enable` and `disable` default to global scope. An unscoped `list` combines
global and exact-current-directory registrations; use `--global` or `--local`
to filter it:

```text
skillset claude enable <name>
skillset claude disable <name>
skillset claude enable <name> --local
skillset claude disable <name> --local
skillset claude list --verbose
skillset claude list --local --verbose
```

Claude Code discovers direct skill directories, so enable creates an absolute
registration in `.claude/.skillsets/<name>` and absolute per-skill links in
`.claude/skills/`. It preserves unrelated entries. It refuses a skill basename
that collides with another entry in the selected scope or with a
different-target entry in the effective global/local scope; the same canonical
target in both scopes is allowed.

Rerun `enable` after adding or removing direct source skill directories. It adds
missing links and removes only stale links owned by that registration; content
changes inside an already linked skill remain live. Disable removes only owned
links, removes the registration last, and leaves the `.claude` containers in
place.

Treat `claude list` as a synchronized-registration check, not a complete
inventory of every skill Claude Code can discover from ancestors, descendants,
plugins, bundled sources, or enterprise configuration. A global enable can
check only the exact current project's local scope; run `claude list` inside
each relevant project to expose later cross-scope collisions.

Keep generated local `.claude/.skillsets` registrations and projected symlinks
out of version control while preserving intentionally committed,
hand-authored `.claude/skills` content. The CLI does not edit `.gitignore`.
Restart the Claude Code session if it does not notice a top-level skills
directory created after the session started.

For an interrupted or partial Claude projection, preserve the registration and
follow the diagnostic: rerun the same scoped `claude enable` to reconcile the
current source or `claude disable` to remove its owned links. Do not use
`doctor` for this recovery; it diagnoses the managed `.agents` layout, not
external `.claude` projections.

## Use Alternate Storage Deliberately

Override `HOME` for one isolated installation:

```text
HOME=/existing/alternate-home skillset list
```

To place named collections outside `~/.agents`, create the destination before
initialization and write a real `~/.agents/config.json`:

```json
{
  "version": 1,
  "skillsets_directory": "/absolute/normalized/path/to/skillsets"
}
```

Point to a dedicated existing real directory outside `~/.agents`, not a symlink,
repository root, single set, `skills/` directory, or individual skill. The
directory contains named set directories; runtime aliases and locks remain
under `~/.agents`. Do not share one configured directory between independently
locked `~/.agents` installations.

## Recover Conservatively

Use `skillset doctor` to aggregate errors and warnings without mutation. Preserve
the only copy of every skill tree and lockfile named in an error before manual
recovery. Inspect all reported original, staged, old, new, and active paths.
Never delete a stale staging record merely to make validation pass.

Run `skillset doctor --fix` only when the user authorizes repair and can answer
its confirmation. It can complete a verified interrupted activation by
retargeting only the `active` and `.skill-lock.json` aliases recorded in its
canonical intent record. It can also recreate a missing advisory lock, restore
the manual empty-lock sentinel, or create an empty version-3 lockfile for a set
whose real `skills/` directory is empty. Outside that verified activation
recovery, it does not repair arbitrary or unverified aliases, choose between
competing copies, delete staging paths, or reconstruct metadata for installed
skills.

After recovery, require both:

```text
skillset doctor
skillset current
```

Then inspect the affected set with `skillset show <name>`.

## Load Completions

```text
source <(skillset completions bash)
source <(skillset completions zsh)
skillset completions fish | source
```

Completion generation itself does not require an initialized layout.
