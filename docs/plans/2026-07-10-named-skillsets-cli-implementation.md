# Named Skillsets CLI Implementation Plan

> **For agentic workers:** Use `subagent-driven-development` to implement one bead at a time with a fresh implementer,
> task review, and orchestrator-side verification. Stop after each completed bead for user approval.

**Goal:** Deliver a safe usable `init`/`create`/`use` core first, then add upstream delegation, inspection, remaining
lifecycle commands, and diagnostics in independently reviewable beads.

**Architecture:** A dependency-free Python 3 executable manages named directories below `~/.agents/skillsets`. Stable
`skills` and lockfile aliases resolve through one atomically replaced `active` symlink. Black-box tests run the executable
with isolated temporary home directories.

**Source of truth:** `docs/specs/2026-07-10-named-skillsets-cli-design.md`

**Tech stack:** Python 3 standard library, Linux filesystem primitives, `unittest`, Jujutsu, and beads-rust (`br`).

## Global constraints

- Linux only; Python 3 standard library only; no package manifest or runtime dependency.
- Production executable: `bin/skillset`; primary black-box tests: `tests/test_skillset.py`.
- Derive managed state from the process home directory. Tests must never mutate the real `~/.agents` directory.
- Follow strict test-driven development: add a focused failing black-box test, verify RED, implement minimally, then
  verify GREEN before the next behavior.
- Preserve the exact storage layout, name grammar, exit statuses, and safety rules in the design specification.
- Every management operation uses the advisory lock. Minimal scope may defer commands, but not integrity safeguards for
  commands already exposed.
- Every command validates the managed layout when introduced. `init` creates it; `doctor` is the deliberate exception
  because its purpose is to report invalid and partial layouts.
- Use upstream vocabulary: `use` and `remove`, never `switch` or `delete`.
- Universal quality gate after every bead: `python3 -m unittest discover -s tests -v` exits 0 with no warnings or errors.
- Run safe verification in the orchestrator, not inside subagents. Review and fix all Critical or Important findings.
- Close and flush the completed bead, report the checkpoint, and wait for approval before beginning the next bead.

## File structure

- `bin/skillset` — executable CLI, layout model, locking, management operations, inspection, and delegation.
- `tests/test_skillset.py` — black-box behavior tests using temporary `HOME` and a fake `npx` where needed.
- `.gitignore` — runtime lock and staging artifacts that must not be committed.
- `README.md` — installation, workflows, diagnostics, and recovery guidance, expanded as features land.

## Bead 1: Safe core MVP — `init`, `create`, `use`

**Deliverable:** The user can adopt the current installation, create empty or cloned sets, and activate a set safely.

**Files:** Create `bin/skillset`, `tests/test_skillset.py`, and `README.md`; modify `.gitignore`.

**Required behavior:**

- Build the black-box subprocess harness around isolated temporary home directories.
- Parse `init NAME`, `create NAME [--from SOURCE]`, and `use NAME`; usage errors exit 2.
- Validate names before path construction and reject set-directory symlinks, collisions, and ambiguous partial layouts.
- `init` adopts existing real skills and version-3 lock state, creates missing empty state, installs stable relative aliases,
  activates the initial set, and rolls back recoverable failures.
- `create` builds an empty set with the documented lock schema or stages an exact clone before atomic placement.
- `use` validates a complete target and atomically replaces only `active` through a temporary relative symlink.
- Hold the Linux advisory lock for each management operation.
- Reject `create` and `use` before initialization and against invalid aliases, active targets, set shapes, or lockfiles;
  cover management lock contention before exposing the commands.
- Cover interrupted staging state, recoverable rollback, and rollback failure that reports concrete recovery paths.
- Add minimal PATH, initialization, creation, activation, and temporary
  `env -u XDG_STATE_HOME npx skills ... -g` usage documentation.

**Acceptance:** All core happy paths and refusal cases are covered by observed RED/GREEN tests; the complete suite passes;
`bin/skillset --help` documents only the commands currently implemented. This is the first usable release checkpoint.

## Bead 2: Managed upstream delegation

**Deliverable:** Skill installation and maintenance can be performed through the wrapper without direct global `npx` use.

**Files:** Modify `bin/skillset`, `tests/test_skillset.py`, and `README.md`.

**Required behavior:**

- Add `skillset skills <arguments...>` with inherited terminal streams and exact upstream exit status.
- Inject global scope for `add`, `list`/`ls`, `remove`/`rm`, and `update`; preserve an existing global flag.
- Reject project scope for those commands with usage exit 2.
- Pass scope-free and unknown commands as specified, including the unknown-command warning.
- Hold the same advisory lock for the entire child-process lifetime.
- Remove `XDG_STATE_HOME` only from the delegated child environment so upstream uses the managed root lockfile alias.
- Reject delegation before initialization or against invalid aliases, active targets, set shapes, or lockfiles.
- Test argument preservation, exit status, Ctrl-C/signal behavior, and contention against another management operation
  with a fake `npx`; make no network requests.

**Dependency:** Bead 1.

## Bead 3: Inspection and everyday usability

**Deliverable:** Users and scripts can identify active sets and inspect set contents.

**Files:** Modify `bin/skillset`, `tests/test_skillset.py`, and `README.md`.

**Required behavior:**

- Add sorted `list`, script-friendly `current`, verbose listing, and `show NAME`.
- Implement the focused scalar frontmatter reader from the specification without a YAML dependency.
- Normalize multiline descriptions and expose malformed entries exactly as specified.
- Keep inspection read-only while acquiring the advisory lock and rejecting uninitialized or invalid managed layouts.

**Dependency:** Bead 2.

## Bead 4: Remaining lifecycle operations

**Deliverable:** Named sets can be renamed and safely removed.

**Files:** Modify `bin/skillset`, `tests/test_skillset.py`, and `README.md`.

**Required behavior:**

- Add inactive and active `rename`, including collision refusal and rollback after failed active retargeting.
- Add `remove NAME`, confirmation, and `--yes`; always reject removal of the active set.
- Reuse name validation, containment, lock, and set-shape checks rather than duplicating safety logic.
- Reject lifecycle operations against uninitialized or invalid managed layouts.
- Cover both recoverable active-rename rollback and rollback failure that reports concrete recovery paths.
- Cover symlink refusal and destructive-path containment with black-box tests.

**Dependency:** Bead 3.

## Bead 5: Diagnostics and hardening

**Deliverable:** The complete specification is implemented, diagnosable, and documented for routine use and recovery.

**Files:** Modify `bin/skillset`, `tests/test_skillset.py`, `README.md`, and `.gitignore` if staging names changed.

**Required behavior:**

- Add non-mutating, lock-protected `doctor` checks and severity-aware exit behavior from the specification. Unlike other
  commands, `doctor` must inspect and report uninitialized, invalid, and partial layouts rather than rejecting them first.
- Report alias, active-target, set-shape, lock-schema, lock/content, and skill-metadata findings in one run.
- Add cross-command invalid-layout and full command-regression coverage; retain the safety tests in their owning beads.
- Retrofit failed-init and failed-active-rename recovery messages to recommend `skillset doctor` now that it exists.
- Finish recovery guidance and replace the temporary direct-`npx` documentation with wrapper-first guidance.
- Review the full implementation against every design-spec section and remove accidental deferred behavior.

**Dependency:** Bead 4.

## Dependency chain and execution

`Bead 1 → Bead 2 → Bead 3 → Bead 4 → Bead 5`

For each bead: mark it in progress, execute only that scope, run the complete test suite in the orchestrator, obtain a
task-scoped review, fix blocking findings, close and flush the bead, commit with Jujutsu, and stop at the checkpoint.