# Named Skillsets CLI Final-Phase Handoff

## Checkpoint

The named skillsets CLI is implemented through lifecycle operations. This
handoff is committed with the checkpoint that adds `rename` and `remove`.

- Completed issue: `agents-qq7.4`
- Next ready issue: `agents-qq7.5` (diagnostics and hardening)
- Source design: `docs/specs/2026-07-10-named-skillsets-cli-design.md`
- Implementation plan: `docs/plans/2026-07-10-named-skillsets-cli-implementation.md`
- Production executable: `bin/skillset`
- Black-box suite: `tests/test_skillset.py`

The latest full orchestrator run passed 71 tests with:

```sh
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Independent closure review found no Critical or Important blockers.

## Implemented command surface

- `init NAME`
- `create NAME [--from SOURCE]`
- `use NAME`
- `rename OLD NEW`
- `remove NAME [--yes]`
- `list [-v|--verbose]`
- `current`
- `show NAME`
- `skills <arguments...>`

The implementation is dependency-free Python 3 and Linux-specific because it
uses `fcntl.flock` and `O_NOFOLLOW` safety checks.

## Safety invariants already locked by tests

- Named sets are real direct children of `~/.agents/skillsets`; names are
  validated before path construction and set-directory symlinks are refused.
- `active`, `skills`, and `.skill-lock.json` use canonical relative symlinks.
- Activation replaces only `active` atomically through
  `.skillset-use.staging`; stale staging is refused by initialization and all
  managed-layout validation.
- Initialization and active rename have fault-injected rollback tests,
  including interrupts, post-syscall ambiguity, rollback failure, concrete
  recovery paths, and preservation of the only data copy.
- Removal always refuses the active set, confirms on stderr unless `--yes` is
  supplied, and never follows set or nested skill symlinks.
- Inspection is lock-protected and read-only. The focused frontmatter parser
  isolates malformed, non-UTF-8, and invalid-Unicode skills.
- Delegation validates the layout, removes `XDG_STATE_HOME` only from the child
  environment, injects global scope safely around `--`, preserves streams,
  signals, arguments, and status, and holds the lock through process exit.

## Remaining work: diagnostics and hardening

Implement ready issue `agents-qq7.5` only, then stop at its checkpoint.

1. Add lock-protected, non-mutating `doctor` behavior. Unlike other commands,
   it must inspect uninitialized, partial, and invalid layouts rather than
   rejecting at the first validation error.
2. Aggregate findings for canonical aliases, active target, set shape,
   version-3 lock schemas, lock entries versus installed skill directories,
   and discovered `SKILL.md` metadata.
3. Distinguish warnings from structural errors. Exit 0 when there are no
   errors; warnings alone must not produce an error exit.
4. Add black-box tests for healthy, uninitialized, partial, structurally
   invalid, metadata-invalid, and warning-only states, plus lock contention and
   strict non-mutation.
5. Add cross-command invalid-layout and full command-regression coverage while
   retaining existing safety tests.
6. Update recovery messages now that `doctor` exists, finish README recovery
   guidance, and review every design-spec section for accidentally deferred
   behavior. Update `.gitignore` only if new persistent staging names appear.
7. Run the full suite in the orchestrator, obtain independent spec and safety
   reviews, fix blockers, close and flush `agents-qq7.5`, and consider closing
   parent epic `agents-qq7` after confirming all children are complete.

## Execution guidance

- Use test-driven development: tests-only subagent, orchestrator RED,
  production subagent, orchestrator GREEN, then independent review subagents.
- Use subagents heavily for parser/diagnostic contract research, tests,
  implementation, and final review; do not let subagents run verification.
- Keep tests isolated under temporary `HOME` directories and make no network
  requests. Do not exercise the user's real `~/.agents` state.
- Reuse existing validation, frontmatter, lockfile, inspection, and lock
  helpers, but keep `doctor` capable of accumulating findings instead of using
  fail-fast `validate_layout` directly.
- Do not install dependencies, commit, push, or start follow-up work without
  explicit user approval.