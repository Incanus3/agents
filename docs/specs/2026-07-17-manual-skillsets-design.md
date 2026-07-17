# Manually Managed Skillsets Design

**Date:** 2026-07-17
**Status:** Approved design; implementation not started

## Summary

Extend `skillset` with an explicit manual-management mode for hand-authored skill collections. A manual skillset has a `skills/` directory and a `.skillset-manual` marker, but no skillset-local `.skill-lock.json`. When active, `~/.agents/.skill-lock.json` points directly to a read-only canonical empty-lock sentinel. This keeps `~/.agents/skills` stable for agent discovery while ensuring upstream `npx skills` does not write managed metadata into manual skills.

The initial use case is the hand-authored `~/.codex/skills/personal` collection. After implementation, it will live at `~/.agents/skillsets/personal/skills` and `~/.codex/skills/personal` will be a symlink to it, making it both always discoverable by Codex and selectable through `skillset use personal`.

This specification supersedes the invariant in `docs/specs/2026-07-10-named-skillsets-cli-design.md` that every valid skillset owns a real lockfile.

## Goals and non-goals

Goals:

- Explicitly recognize healthy hand-managed sets without silently accepting incomplete managed state.
- Keep manual sets lock-free while presenting a protected lock path to upstream tooling.
- Switch managed and manual sets safely, preserving current behavior for managed sets.
- Mark manual sets compactly in both list formats: `[m]`, colorized on eligible TTYs.
- Make manual mode, diagnostics, and recovery self-explanatory.

Non-goals:

- Manage manual skills through `npx skills`.
- Infer manual mode solely from a missing lockfile.
- Make direct `npx` invocations participate in `skillset`'s advisory lock.
- Move the real `personal` directory before the feature has passed verification.

## Filesystem contract

A managed skillset is unchanged:

```text
~/.agents/skillsets/always-on/
├── skills/
└── .skill-lock.json              # real, valid upstream lockfile
```

A manual skillset is deliberately lock-free:

```text
~/.agents/skillsets/personal/
├── skills/
└── .skillset-manual              # real, empty regular marker file
```

The tool owns one shared sentinel outside all sets:

```text
~/.skillset-manual-empty-lock.json
```

It is a real regular file containing the canonical empty upstream lock JSON:

```json
{"version": 3, "skills": {}, "dismissed": {}}
```

`skillset` creates it with mode `0444`, validates its exact empty-lock semantics before selecting manual mode, and never writes it after creation. `skillset use` recreates a missing sentinel when activating or retaining a manual set; `doctor --fix` offers the same safe repair after confirmation. It lives outside the repository-backed `~/.agents` tree so version-control tools do not attempt to rewrite it during commits. This is an immutable tool contract, not an absolute filesystem guarantee: the owning user can still replace a file in a writable parent directory.

Root aliases are mode-aware:

```text
# Managed active set
active            -> skillsets/always-on
skills            -> active/skills
.skill-lock.json  -> active/.skill-lock.json

# Manual active set
active            -> skillsets/personal
skills            -> active/skills
.skill-lock.json  -> ../.skillset-manual-empty-lock.json
```

Thus a manual set itself has no lock path, while the upstream canonical root lock path always exists. In manual mode, upstream writes reach the protected empty sentinel rather than creating lock metadata in the skillset.

## Classification and validation

Every direct child of `skillsets/` is classified before inspection or mutation:

| Classification | Required state | Result |
| --- | --- | --- |
| Managed | real `skills/`; no marker; real valid `.skill-lock.json` | Valid |
| Manual | real `skills/`; real empty `.skillset-manual`; no `.skill-lock.json` | Valid |
| Invalid | missing or malformed required entries, marker symlink/nonempty/non-regular, both marker and lockfile, or missing lock without marker | Refuse and diagnose |

Set and `skills/` directories retain the current real-directory and direct-child rules. The marker is a real zero-byte regular file, never a symlink. A marker plus any lockfile—including a symlink—is invalid: manual mode must remain structurally lock-free.

`validate_layout` checks the root lock alias according to the active mode. A managed set requires `active/.skill-lock.json`; a manual set requires `../.skillset-manual-empty-lock.json` and a valid read-only sentinel at `~/.skillset-manual-empty-lock.json`. `skills -> active/skills` remains constant.

## Command semantics

### Lifecycle

- `skillset create --manual NAME` creates `skills/` and `.skillset-manual`, with no lockfile.
- `skillset create NAME` keeps its current managed behavior and creates an empty upstream lockfile.
- `skillset create NAME --from SOURCE` preserves the source mode: managed copies a lockfile, manual copies the marker and has no lockfile.
- `--manual` and `--from` are mutually exclusive, so a managed source cannot ambiguously become manual.
- `rename` and `remove` accept either valid mode, preserving active-set restrictions.
- `init` remains a managed-layout adoption command; it never infers or creates manual state.

### Activation and recovery

Switching modes changes both `active` and the root `.skill-lock.json` alias. `use` will therefore replace the existing single-link staging flow with a persisted transaction:

1. Validate the current layout and requested target mode.
2. Write a canonical `.skillset-use.staging` record containing old and requested targets for both aliases, with controlled replacement symlinks.
3. Replace both aliases in a defined order.
4. Remove the record only after the new pair is fully valid.

If interruption or an error occurs after the record is durable, retain it and refuse normal commands. `skillset doctor --fix` asks for confirmation, validates the canonical recorded intent and current link state, then completes the requested activation. Malformed or noncanonical staging state is diagnosed but never guessed at. Managed-to-managed switching may use this same path for a uniform recovery contract.

### Delegated upstream commands

`skillset skills add`, `remove`/`rm`, and `update` refuse while a manual set is active, before invoking `npx`. The diagnostic says the active set is manually managed and must be maintained by editing its files. The first implementation should reject all lock-aware delegated commands for a manual active set; scope-free pass-through commands such as `find` and `use` retain current behavior.

The read-only sentinel is a second defense for direct `npx skills` use. Direct upstream use remains discouraged because it cannot honor the wrapper lock and future upstream write strategies may not preserve this protection.

## Inspection and diagnostics

`skillset list` retains lexical order and the active `* ` prefix. It adds `[m]` only after manual names:

```text
* always-on
personal [m]
```

`[m]` is yellow when existing TTY-color policy permits and plain otherwise. It is a compact mode suffix, rather than a
spelled-out management label.

Verbose listing adds the same suffix after the padded name cell and before the separator:

```text
  SKILLSET     | SKILLS
  -------------|----------------
* always-on    | onevcat-jj
  personal [m] | feature-status
```

The left-column width and separator include the compact suffix where present, so every table delimiter remains aligned.
Using `[m]` rather than `[manual]` limits the mode annotation to four additional display cells. The active marker and name
remain bold cyan; only `[m]` is yellow.

`skillset show personal` prints `Manual skillset [m]: no upstream lock metadata.` before its existing table or empty message. Managed `show` output remains byte-for-byte unchanged.

`doctor` accepts valid manual sets, validates the marker and sentinel, validates the active root lock target, and never proposes creating a lockfile inside a marked manual set. An unmarked missing lockfile remains an error. Existing narrowly safe lockfile repair still applies only to genuinely managed empty sets.

## Migration

After the feature is implemented and verified:

1. Create `~/.agents/skillsets/personal/` as a manual skillset.
2. Move `~/.codex/skills/personal` to `~/.agents/skillsets/personal/skills` without changing the handmade skills.
3. Replace `~/.codex/skills/personal` with a symlink to that `skills/` directory.
4. Verify `skillset doctor`, `skillset list`, `skillset show personal`, `skillset use personal`, and Codex skill discovery through `~/.codex/skills/personal`.

The Codex link keeps `personal` always discoverable whether or not it is the active `.agents` skillset.

## Implementation boundaries

- `lib/skillset/layout.py`: classify modes; validate/create marker and sentinel; validate mode-aware aliases.
- `lib/skillset/operations.py`: create/clone manual sets and implement the durable two-alias switch.
- `lib/skillset/delegate.py`: block lock-aware upstream delegation in manual mode.
- `lib/skillset/metadata.py`: carry mode into list/show and render the `[m]` suffix and notice.
- `lib/skillset/doctor.py`: diagnose manual state, sentinel state, and interrupted switches; recover only verified staged switches under `--fix`.
- `lib/skillset/cli.py` and completions: add `create --manual` and reject its combination with `--from`.
- `README.md`: document manual mode, `[m]`, upstream restriction, and migration.
- `tests/test_skillset.py`: add black-box, PTY-color, and fault-injection coverage.

## Verification

Tests must cover valid and invalid mode combinations; exact plain and TTY list output; no verbose name-column widening; manual `show`; both activation directions; injected failures between alias replacements and confirmed `doctor --fix` recovery; manual creation/cloning/rename/remove; refusal before fake `npx` executes; no manual lockfile repair; and the isolated-home `personal` migration topology.

Run focused tests during development, then:

```bash
python3 -m unittest discover -s tests -v
```

Only after a green suite and diff review may the real-home migration be performed.

## Rejected alternatives

- **Treat any missing lock as manual:** masks incomplete managed state.
- **Put an empty-lock symlink in every manual set:** adds a second link, requires a brittle two-directory upward target, and makes manual sets no longer structurally lock-free.
- **Keep the root lock alias fixed through `active`:** cannot provide both a lock-free manual set and a protected upstream lock path.
- **Use `XDG_STATE_HOME` isolation:** splits visible files from upstream metadata and does not consistently protect direct upstream use.
- **Use `[manual]` in list output:** needlessly widens the scarce first column; `[m]` is sufficient, with `show` giving the full explanation.
