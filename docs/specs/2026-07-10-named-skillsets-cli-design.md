# Named Skillsets CLI Design

**Date:** 2026-07-10
**Status:** Approved design; implementation not started

## Clean-session summary

Build a Linux-only, dependency-free Python 3 command named `skillset`. It will manage mutually exclusive named groups
of global agent skills under `~/.agents/skillsets`, activate them through one atomic `active` symlink, and delegate skill
installation and maintenance to `npx skills`.

The key design correction discovered during research is that a skillset cannot contain only skill files. The upstream
CLI stores global update/remove metadata separately in `~/.agents/.skill-lock.json`, so each set must own both its
`skills/` directory and its lockfile. Stable root aliases expose both parts of the active set.

All product decisions are recorded below. There are no unresolved product questions. Start implementation with tests;
do not redesign the command surface unless implementation evidence contradicts an assumption in this document.

## Motivation

The user wants to compare complete agent-skill frameworks, including agent-skills, Superpowers, and Matt Pocock's skill
collection. These frameworks can contain competing router skills, command names, and development philosophies. The
comparison that motivated this work recommends one active primary router at a time rather than stacking frameworks:

- <https://github.com/addyosmani/agent-skills/blob/main/docs/comparison.md>

Named skillsets make those experiments repeatable while retaining `npx skills` as the installer and updater.

## Repository and machine context

- The repository root is the user's existing `~/.agents` directory.
- The repository was newly initialized around existing files. The existing `skills/` baseline is committed separately
  from this specification before implementation begins.
- At design time, `skills/` is a real directory and `.skill-lock.json` is a real version-3 global lockfile.
- Existing `~/.augment/skills/<name>` entries are relative symlinks to `../../.agents/skills/<name>`. Keeping
  `~/.agents/skills` as a stable path preserves this topology across active-set changes.
- The repository has no application scaffold or package manifest. The implementation must not add a runtime package
  dependency.
- Python 3 and Linux are the only first-version platform requirements. Node is available because delegation uses `npx`,
  but the management CLI must not be implemented in Node.
- The executable is tracked at `~/.agents/bin/skillset`; the user will add `~/.agents/bin` to `PATH` separately.

## Upstream `npx skills` learnings

Research used the current `vercel-labs/skills` documentation and source:

- CLI documentation: <https://github.com/vercel-labs/skills>
- Lock implementation: <https://github.com/vercel-labs/skills/blob/main/src/skill-lock.ts>

Relevant behavior:

- Global canonical skills are stored under `~/.agents/skills` and can be linked into agent-specific global directories.
- The default global lock path is `~/.agents/.skill-lock.json`. If `XDG_STATE_HOME` is set, upstream instead uses
  `$XDG_STATE_HOME/skills/.skill-lock.json`.
- The lockfile records sources and folder hashes used by update/remove workflows; sharing one lockfile across sets would
  make active files and upstream metadata disagree.
- Upstream writes the lockfile through its configured path, so a root lockfile symlink is compatible with normal writes.
- `add`, `list`, `remove`, and `update` support global scope. `find`, `use`, and upstream `init` are not installed-skill
  scope operations.
- The upstream package is intentionally not pinned by this wrapper. `skillset skills ...` invokes the user's normal
  `npx skills` resolution and does not add `npx --yes`.

The design deliberately does not use `XDG_STATE_HOME` virtualization: that would make direct `npx skills` calls consult
different metadata from the wrapper and would leave only part of the active state represented by filesystem aliases.

## Goals

- Keep every named set's skill files and upstream lock metadata together.
- Activate a set's files and metadata as one logical operation.
- Preserve existing agent links through the canonical `~/.agents/skills` path.
- Make management safe against path traversal, interruption, and concurrent wrapper use.
- Preserve interactive upstream CLI behavior and exit status.
- Support useful inspection without introducing a YAML dependency.

## Non-goals

- Native macOS or Windows support in the first version.
- Refreshing skills already loaded into a running agent session.
- Repairing malformed layouts or lockfile/content mismatches automatically.
- Managing project-local skills through the wrapper.
- Reimplementing upstream installation, discovery, update, or removal.
- Cleaning agent-specific links outside `~/.agents`; dangling links for skills absent from the active set are harmless.

## Filesystem architecture

Managed state lives under `~/.agents`:

```text
~/.agents/
├── active -> skillsets/default
├── skills -> active/skills
├── .skill-lock.json -> active/.skill-lock.json
├── .skillset.lock
├── bin/skillset
└── skillsets/
    ├── default/
    │   ├── skills/
    │   └── .skill-lock.json
    └── experiment/
        ├── skills/
        └── .skill-lock.json
```

`active`, `skills`, and `.skill-lock.json` are relative symlinks. Activation atomically replaces only `active`; the two
stable aliases do not change. Existing links such as `~/.augment/skills/<skill> -> ../../.agents/skills/<skill>` then
resolve through the active set automatically.

Every set directory is a real direct child of `skillsets/`, not a symlink. Names match `[a-z0-9][a-z0-9_-]*`; dots,
uppercase characters, whitespace, separators, and traversal components are rejected.

An empty lockfile uses the current upstream global schema:

```json
{"version": 3, "skills": {}, "dismissed": {}}
```

## Command surface

### Initialization and lifecycle

- `skillset init NAME` initializes management and activates `NAME`. It moves an existing real `skills/` directory and
  real `.skill-lock.json` into the new set. If either is absent, it creates the corresponding empty state. Existing
  symlinks or a partial managed layout are ambiguous and rejected with recovery guidance.
- `skillset create NAME` creates an empty inactive set.
- `skillset create NAME --from SOURCE` clones the source set's complete `skills/` tree and lockfile.
- `skillset use NAME` validates the set and atomically replaces `active`.
- `skillset rename OLD NEW` renames an inactive set directly. For the active set, it renames and retargets `active`,
  rolling the directory rename back if retargeting fails.
- `skillset remove NAME` removes an inactive set after confirmation. `--yes` skips confirmation. Removing the active set
  is always rejected; the user must activate another set with `skillset use` first.

Commands other than `init` require a valid managed layout. No create, init, or rename command overwrites a target.

### Inspection

- `skillset list` prints sets in name order, one per line, and marks the active set with `*`.
- `skillset list -v` and `skillset list --verbose` append sorted valid declared skill names on the same line. Empty sets
  show `(no skills)`; malformed entries are omitted here and remain visible through `show` and `doctor`.
- `skillset current` prints only the active set name plus a newline, suitable for command substitution.
- `skillset show NAME` prints sorted skills, one per line, as `<name> — <description>`. Invalid entries remain visible as
  `<directory> — [invalid: <reason>]`.
- `skillset doctor` validates the complete layout and reports every detected problem without changing files.

### Upstream delegation

`skillset skills <arguments...>` delegates to `npx skills <arguments...>` with inherited stdin, stdout, stderr, signals,
and exit status.

For `add`, `list`/`ls`, `remove`/`rm`, and `update`, the wrapper injects `--global` unless `-g` or `--global` is already
present. It rejects `-p` and `--project` for these commands. Scope-free commands such as `find`, `use`, and upstream
`init` pass through unchanged. Unknown future commands also pass through unchanged after a stderr warning that global
scope was not injected.

The wrapper does not reinterpret upstream options or output. Management commands never invoke `npx`, and delegated
commands never intentionally alter the skillset structure.

## Frontmatter inspection

Inspection walks direct children of a set's `skills/` directory. A skill is a directory containing `SKILL.md` with
opening and closing YAML frontmatter delimiters and top-level `name` and `description` fields.

The focused parser supports plain, single-quoted, double-quoted, literal (`|`), and folded (`>`) scalar values for those
two fields. It normalizes multiline descriptions to one display line by collapsing whitespace. It is not a general YAML
parser. Unsupported or malformed values are shown as invalid and reported by `doctor`; they do not prevent other skills
from being listed.

## Safety and failure handling

- Management and delegated operations acquire an exclusive Linux advisory lock at `~/.agents/.skillset.lock`.
- Delegation holds the lock for the lifetime of `npx skills`; direct `npx skills` use cannot honor this lock and is
  discouraged after initialization.
- Create and clone build a temporary sibling directory and rename it into place only when complete.
- `use` creates a temporary relative symlink and uses `os.replace` for the atomic change.
- Every destructive path is constructed only after name validation and checked to remain a direct child of
  `skillsets/`.
- Remove refuses set-directory symlinks and never follows them.
- Initialization and active rename perform explicit rollback where possible. If rollback cannot restore a valid layout,
  the command reports concrete paths and directs the user to `doctor`; it does not guess or auto-repair.
- Usage errors exit 2. Operational or validation failures exit 1. Successful management commands exit 0. Delegated
  commands return the upstream process status.

The persistent advisory-lock file is ignored by version control. Changing the active set only affects discovery for future
agent sessions.

## Doctor semantics

`doctor` checks the stable aliases, active target, set directory shape, version-3 JSON lockfiles, lock entries versus
installed directories, and each discovered skill's `SKILL.md` metadata. It reports all findings in one run and exits 0
when no errors are found. Warnings, such as an installed skill absent from the lockfile, are distinguished from
structural errors and do not trigger mutation.

## Implementation boundaries and file plan

Keep units small even if the production implementation remains one executable:

- `bin/skillset`: executable Python 3 CLI, argument parsing, layout model, operations, inspection, locking, and upstream
  process delegation. Use only the standard library (`argparse`, `fcntl`, `json`, `os`, `pathlib`, `shutil`, and
  `subprocess` as needed).
- `tests/test_skillset.py`: black-box `unittest` suite invoking the real executable under temporary `HOME` directories.
- `.gitignore`: ignore `.skillset.lock` and operation staging paths if persistent names are used.
- `README.md`: PATH setup, initialization, lifecycle examples, delegated command examples, and recovery/doctor guidance.

Do not add a package manifest or install PyYAML. Do not make tests import or mutate the user's actual `~/.agents` state.
The CLI should derive its root from the process home directory so tests can isolate it by setting `HOME`.

For delegated commands, do not capture standard streams. Keep the advisory lock in the parent for the child lifetime or
explicitly preserve the lock descriptor across process replacement. Verify Ctrl-C and nonzero status behavior with the
fake upstream executable.

## Test strategy

Follow test-driven development. Black-box standard-library `unittest` tests execute the real CLI with temporary fake
home directories. A fake `npx` binary records delegated arguments and returns controlled statuses. Tests make no network
requests and never modify the real home directory.

Coverage includes:

- Initialization from existing files, initialization from empty state, rollback, and ambiguous-state refusal.
- Empty creation, exact cloning, duplicate names, invalid names, and missing clone sources.
- Repeated `use` operations and stable root alias targets.
- Active and inactive rename, target collisions, and rollback behavior.
- Guarded removal, active-set refusal, confirmation, and `--yes`.
- Sorted `list`, verbose listing, `current`, and detailed `show` output.
- Plain, quoted, literal, folded, missing, and malformed frontmatter values.
- `doctor` structural errors, metadata errors, lock/content warnings, and exit statuses.
- Lock contention between management operations and delegated operations.
- Global-flag injection, existing global flags, project-flag rejection, argument preservation, warnings for unknown
  commands, interactive stream inheritance, and delegated exit status.

The intended verification command is:

```bash
python3 -m unittest discover -s tests -v
```

## Accepted trade-offs

- One extra `active` indirection is preferable to retargeting the root skills and lockfile links separately; it prevents
  normal activation from exposing mismatched state.
- Python is preferable to Bash because migration, rollback, containment checks, frontmatter parsing, and black-box tests
  are clearer and safer. The cost is requiring Python 3.
- A focused frontmatter parser is sufficient for normal skill metadata. Full YAML support is not worth a dependency.
- Unknown upstream commands remain forward-compatible but cannot safely receive an assumed scope flag; the warning makes
  that limitation explicit.
- Advisory locking protects wrapper use, not direct concurrent `npx skills` calls. Documentation is the mitigation.
- Active rename cannot make both directory rename and symlink retarget one indivisible filesystem operation. Explicit
  rollback and `doctor` are the mitigation.

## Implementation-session checklist

1. Read this document and inspect the two baseline commits; do not infer requirements from the old spec path.
2. Confirm the current upstream command flags if `npx skills` has materially changed since this design date.
3. Read the test-driven-development skill before production work.
4. Write the first failing black-box tests for initialization and layout invariants.
5. Implement in small vertical slices: init/layout, inspection, lifecycle, delegation/locking, then documentation.
6. Run the focused test suite after each slice and the complete command above before claiming completion.
7. Never run `skillset init` against the real home directory during development or tests.

## Documentation requirements

Repository documentation must show how to add `~/.agents/bin` to `PATH`, initialize the existing installation, create an
empty or cloned experiment, activate it with `skillset use`, inspect contents, run `doctor`, and use `skillset skills`
instead of direct global `npx skills` commands.