---
name: workstreams
description: "List current and ready repository workstreams by merging indexed handoffs with live br task state into a concise read-only overview. Manual invocation only: apply only if the user explicitly invokes `$workstreams`; never select automatically from a natural-language request."
---

# List repository workstreams

Produce a source-neutral, read-only overview. Do not edit handoffs, update task state, continue a
workstream, or perform version-control writes.

## Collect current work

1. Read repository guidance and `docs/handoffs/INDEX.md` when present.
2. Read every indexed handoff. Extract its slug, recorded status, objective, first explicit next
   action, and exact linked `br` issue ID when present.
3. When a `br` workspace exists, query live state with:
   - `br list --status in_progress --json`;
   - `br blocked --json`;
   - `br ready --json`;
   - `br show <id> --json` for linked or included issues whose priority or next action is needed.
4. Keep the entire operation read-only. If `br` is absent or uninitialized, list handoff-backed
   workstreams without bead enrichment.

## Merge and normalize

Merge each handoff with the exact `br` issue it references. Never show the linked handoff and bead as
separate workstreams. Exclude linked issue IDs from bead-only in-progress and pending candidates.

Use exactly one source-neutral state per entry:

- map a handoff or any included linked bead with a current blocker to `blocked`;
- otherwise preserve handoff `parked`;
- otherwise map handoff `active` to `in-progress`;
- map a bead-only `in_progress` issue to `blocked` when live blocked output contains it, otherwise to
  `in-progress`;
- map a ready, unstarted bead selected for the overview to `pending`.

Apply that precedence in the listed order. A parked handoff linked to an open or ready bead is not a
conflict by itself: handoff focus and bead readiness describe different scopes. If the sources
conflict materially, such as a live blocker overriding an active handoff or a closed bead linked from
an unfinished handoff, use the normalized live state and append a short warning. Do not invent a
fifth normal state or repair the inconsistency.

## Select entries

1. Include every handoff-backed workstream.
2. Include every additional bead-only in-progress workstream. Never truncate either group.
3. Count all entries whose normalized state is `in-progress`.
4. Show no pending beads when that count is five or greater.
5. Otherwise, if fewer than eight non-pending entries exist, append the highest-priority eligible
   pending beads until the overview contains eight workstream lines. Do not impose another pending
   cap.
6. Deduplicate all selected bead IDs. When eligible pending beads were omitted, report how many.

Order non-pending entries as `in-progress`, `blocked`, then `parked`; within a state, sort by numeric
priority when known and then identity. Place pending entries last, sorted by numeric priority while
preserving a stable order for ties.

## Format the overview

Number the selected entries consecutively from 1 in their final displayed order. Use one physical
line per workstream when practical:

```text
1. [parked · P1] session-capture-v0 — Decide the completed five-run capture trial. Next: choose retain, revise, automate, or reject.
```

- Treat the numbers as ephemeral selectors for an immediately following `$resume <n>` invocation,
  not as persistent workstream identifiers.
- Put state and priority inside the opening brackets. Omit `· Pn` when no bead supplies a priority.
- Use the handoff slug for a merged workstream and the bead ID for a bead-only workstream.
- Use the handoff objective or bead title as the concise description.
- Use the first explicit handoff next action or current bead evidence for `Next:`. Write
  `Next: unknown` rather than inventing an action.
- Do not expose raw source labels such as `handoff`, `br`, `open`, or `ready` as additional states.

After a non-empty overview, report `Resume with $resume <n>.` If no entries exist, report
`No current or ready workstreams.` without the resume hint.
