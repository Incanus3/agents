---
name: status
description: "Report the concise recorded status of a workstream from its indexed handoff without refreshing live systems or continuing the work. Manual invocation only: apply only if the user explicitly invokes `$status` with or without a workstream slug; never select automatically from a natural-language request."
---

# Report recorded workstream status

Remain strictly read-only. Do not edit the handoff or index, refresh task or workspace state, make
version-control changes, or continue the workstream.

## Resolve the handoff

1. Read the repository guidance and `docs/handoffs/INDEX.md`.
2. For `$status <slug>`, require an exact lowercase kebab-case slug and an exact indexed match.
   Reject paths, `.md` suffixes, malformed slugs, and fallback to similarly named entries.
3. For bare `$status`:
   - report that no active handoff exists when the index has no live entries;
   - select the sole live entry when exactly one exists;
   - when several exist, list their slugs and one-line purposes, ask the user to choose, and stop.
4. Read only the selected handoff. Treat an absent file or index/file mismatch as an inconsistency;
   report it instead of guessing.

## Report

Summarize the handoff as recorded:

- workstream slug and objective;
- recorded status and updated date;
- current phase or checkpoint;
- the next one to three actions;
- blocker and reason, if blocked;
- pending decision, prerequisite, or human gate.

Mark missing fields as `unknown`; do not infer them from external or live state. Optionally name the
primary durable references needed for context. Explicitly say that the result is recorded status,
not freshly verified live state.
