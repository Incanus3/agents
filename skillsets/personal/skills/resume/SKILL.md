---
name: resume
description: "Reorient to a named workstream from its indexed handoff, refresh relevant live state, reconcile stale statements, and continue the recorded next action. Manual invocation only: apply only if the user explicitly invokes `$resume` with or without a workstream slug; never select automatically from a natural-language request."
---

# Resume a workstream

Use the handoff as a short-lived recovery aid, not as proof of current state. Refresh the relevant
authoritative systems before continuing.

## Resolve the handoff

1. Read the repository guidance and `docs/handoffs/INDEX.md`.
2. For `$resume <slug>`, require an exact lowercase kebab-case slug and an exact indexed match.
   Reject paths, `.md` suffixes, malformed slugs, and fallback to similarly named entries.
3. For bare `$resume`:
   - report that no active handoff exists when the index has no live entries;
   - select the sole live entry when exactly one exists;
   - when several exist, list their slugs and one-line purposes, ask the user to choose, and stop.
4. Treat an absent file or index/file mismatch as an inconsistency; report it instead of guessing.

## Reorient and refresh

1. Read the selected handoff and only the durable references needed for its immediate next action.
2. Refresh the relevant live task, workspace, and version-control state. Follow repository tool
   precedence and safety guidance before the first version-control inspection. Refresh external
   systems only when the handoff or next action depends on them.
3. Compare the live evidence with the recorded checkpoint. Reconcile each stale statement in the
   system that owns it. If only the handoff's resume delta is stale, update only the handoff; never
   mutate authoritative state merely to make it match the handoff.
4. State the recovered objective, checkpoint, and immediate next action.
5. Continue the work unless a recorded human gate or newly discovered blocker requires input.

Do not copy durable specifications, task state, full logs, or transient dirty-file lists into the
handoff. Preserve the selected slug for subsequent `$handoff` use.

## Complete the workstream

When the workstream finishes, first persist durable results and evidence, then close or update its
authoritative tasks. Delete `docs/handoffs/<slug>.md` and its index entry in the same change unless a
specific recovery need remains. Do not keep a handoff archive by default.
