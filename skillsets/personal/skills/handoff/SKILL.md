---
name: handoff
description: "Create or update the short-lived handoff for a named workstream and return its copy-ready resume command. Manual invocation only: apply only if the user explicitly invokes `$handoff` with or without a workstream slug; never select automatically from a natural-language request."
---

# Create or update a workstream handoff

Treat the workstream slug as the public identity. Store it internally at
`docs/handoffs/<slug>.md`, and keep `docs/handoffs/INDEX.md` synchronized.

## Resolve the workstream

1. Read the repository guidance and its handoff workflow when present.
2. For `$handoff <slug>`, require an exact lowercase kebab-case slug. Reject paths, `.md`
   suffixes, malformed slugs, and silent fallback to a similar name.
3. For bare `$handoff`, reuse the slug from which the current session resumed. If the session did
   not resume from a handoff, derive a meaningful non-colliding slug and report it. Never overwrite
   an unrelated handoff.
4. Update an existing matching handoff in place; otherwise create its file and index entry.

## Preserve authority

Before writing the handoff, harvest durable results into their owning systems:

- specifications, decisions, reusable findings, and experiment evidence into canonical documents;
- repository-local tasks, dependencies, and evidence into the repository task tracker;
- higher-level commitments into their designated system when it is operational.

Link those authorities from the handoff. Do not copy their full content or turn the handoff into a
task tracker.

## Write only the resume delta

Keep the handoff concise and current. Include:

- status (`active`, `blocked`, or `parked`), updated date, and `$resume <slug>`;
- objective and intended outcome;
- durable references, including the relevant task identifier when one exists;
- current checkpoint and what is already complete;
- immediate next actions in order;
- blockers, pending decisions, prerequisites, and constraints;
- failed attempts or temporary assumptions only when needed to prevent repeated work.
- relevant skill requirements or environment cautions when they materially affect continuation.

Do not include secrets, chat transcripts, full logs, copied acceptance criteria, or a transient list
of dirty files. Keep important version-control cautions only when they materially affect recovery.

## Synchronize and verify

Add or update one grep-friendly line in `docs/handoffs/INDEX.md` with the file link, recorded state,
purpose, and the command that uses it. Verify that linked durable references resolve and that the
handoff contains no sensitive or duplicated canonical material.

Finish by returning the copy-ready command `$resume <slug>` without block-quote formatting. Do not
commit, push, or alter unrelated task state unless separately requested.
