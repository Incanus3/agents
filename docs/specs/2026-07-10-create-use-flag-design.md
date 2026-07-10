# Activate a Newly Created Skillset

**Date:** 2026-07-10
**Status:** Approved design; implementation not started

## Context

The Linux-only `skillset` CLI manages named global skill collections under
`~/.agents/skillsets`. `skillset create NAME` currently creates an inactive empty set,
while `skillset create NAME --from SOURCE` clones an inactive set. Activating either
requires a separate `skillset use NAME` command.

The create operation stages a complete set and atomically renames it into place. The
use operation separately validates a set and atomically replaces the `active` symlink.
Both operations run under stable HOME and managed-layout advisory locks.

## Requirement

Add `--use` to `skillset create` so a successfully created set can be activated by the
same CLI invocation.

All of these forms must work:

```text
skillset create NAME --use
skillset create --use NAME
skillset create NAME --from SOURCE --use
skillset create --use --from SOURCE NAME
```

Normal `argparse` option intermixing should support options before or after the `NAME`
positional argument. The implementation must not impose a custom order.

Without `--use`, create remains backward compatible and leaves the current set active.

## Design

Add a boolean `--use` argument to the create subparser. CLI dispatch will compose the
existing operations while retaining the locks already held for the command:

1. Call `create(root, name, source)`.
2. If creation succeeds and `--use` was provided, call `use(root, name)`.
3. Return success only when every requested operation succeeds.

The `create` and `use` operation contracts remain independent. No activation parameter
or combined transaction is added to `create`, and no activation logic is duplicated.
The stable root `skills` and `.skill-lock.json` aliases remain unchanged; activation
continues to replace only the `active` symlink atomically.

## Error and interruption semantics

- If create validation, staging, copying, or placement fails, activation is not
  attempted and the existing create recovery behavior is preserved.
- Once create places the destination set, that creation is committed.
- If subsequent activation fails before its atomic replacement, the new set remains
  present and the previously active set remains active. The command reports the
  existing activation error and exits unsuccessfully.
- An interrupt before replacement has the same data and active targets, but existing
  `use` behavior may retain its canonical `.skillset-use.staging` marker for diagnosis.
- If an exception or interrupt is observed after the atomic active replacement, the
  new set is active because activation has committed. Existing `use` outcome and
  recovery semantics are preserved.
- No failure path deletes the newly created set or attempts a combined rollback.

These rules intentionally match running `skillset create ...` followed by
`skillset use NAME`, except both steps retain one command's advisory locks.

The valid state boundaries are therefore: before create commits, no destination is
promised; after create commits but before use commits, the destination exists and the
old set is active; after use commits, the destination exists and is active. Any retained
canonical staging marker remains persistent recovery state and must not be silently
removed by CLI-level orchestration.

## Rejected alternatives

### Composite operation

A new `create_and_use` operation would centralize orchestration but add an abstraction
used by only one dispatch path. CLI-level composition is clearer and preserves the
existing focused operations.

### Activation parameter on create

Adding activation behavior to `create` would couple set construction to active-alias
management and make its failure contract less focused.

### All-or-nothing rollback

Deleting the new set when activation fails would require safely removing a complete
empty or cloned tree. It would also differ from the intuitive sequential command
semantics and risk destroying a successfully created result.

## File boundaries

- `lib/skillset/cli.py`: parse `--use` and compose existing create/use calls.
- `tests/test_skillset.py`: add black-box command, ordering, state, and fault tests.
- `README.md`: document creation with immediate activation and both empty/clone usage.
- `lib/skillset/operations.py`: no behavioral change expected.

## Verification strategy

Tests must demonstrate:

1. Empty `create --use` creates and activates the named set.
2. Cloned `create --from SOURCE --use` preserves the complete source tree and lockfile
   and activates the clone.
3. Options work before and after the `NAME` positional argument.
4. Create without `--use` still leaves the previous set active.
5. A create failure never changes the active target.
6. An injected activation failure returns failure, retains the complete new set, keeps
   the previous active target, and leaves stable aliases unchanged.
7. A fault observed after active replacement preserves the committed new active target
   and does not remove the new set.
8. CLI help exposes `--use`, while unknown options still produce argparse exit status
   2.

Run the focused test cases first, followed by the complete existing test suite. Run
`skillset doctor` only against test HOME directories; development must never initialize
or mutate the real HOME layout during verification.

## Repository state and next-session checklist

The implementation starts from the modular CLI in `lib/skillset`, with black-box tests
in `tests/test_skillset.py`. At design time, the working copy also contains an unrelated
uncommitted `skillsets/minimal/.skill-lock.json`; implementation must not modify or
remove it.

Before implementation:

1. Read this specification and the current create/use tests.
2. Follow test-driven development: add failing black-box tests before production code.
3. Make the minimal parser and dispatch change; do not broaden operation contracts.
4. Update README examples and run focused, then complete verification.
