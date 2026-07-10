# Describe `create --from` in Help

**Date:** 2026-07-10
**Status:** Approved design; implementation not started
**Tracking:** `agents-xnq`

## Context

`skillset create -h` renders `--from SOURCE` without explanatory text because the
argument declaration has no `help=` value. The adjacent `--use` option has a description,
making the omission visible and leaving users to infer what `SOURCE` means.

The existing black-box create-help test verifies only that `--use` appears.

## Requirement

The create-subcommand help must render this option and description:

```text
--from SOURCE  clone from an existing skillset
```

The exact wording is user-approved. Command behavior, parsing, option order, exit
statuses, and filesystem state must remain unchanged.

## Design

Add `help="clone from an existing skillset"` to the existing `--from` argument in
`lib/skillset/cli.py`. Extend the existing black-box create-help test to assert that the
description appears in stdout.

This direct argument help is preferred because `argparse` associates the description
with the option in the standard options table. A create-parser description would be
less specific, and README-only documentation would not fix command discoverability.

## Error and state semantics

Help parsing exits before HOME layout access, locking, or filesystem mutation. The
change adds no operational path and must preserve help exit status 0.

## File boundaries

- `lib/skillset/cli.py`: add the exact `--from` help text.
- `tests/test_skillset.py`: lock the help description with a black-box assertion.
- No README change is required because cloning is already documented there.

## Verification

1. Add the assertion before production code and confirm focused RED because the text is
   absent.
2. Add the exact help string and confirm focused GREEN.
3. Run the complete unittest suite with exit status 0 and no warnings or errors.
4. Review the diff for accidental parsing or product-surface changes.

## Repository state

This bead builds on the uncommitted, verified `agents-023` changes for `create --use`.
The unrelated pre-existing `skillsets/minimal/.skill-lock.json` addition must remain
untouched. No commit may be created without explicit user permission.
