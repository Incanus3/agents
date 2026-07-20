---
name: handoff
description: Create or update a detailed handoff document for the current work and produce a concise continuation prompt. Manual invocation only: apply only if the user explicitly invokes `$handoff`; never select automatically from a natural-language request.
---

If work is already based on a handoff file, update that handoff. Otherwise, or when explicitly
asked, create a new meaningful handoff under `docs/handoffs/` based on the work completed.

Keep the handoff fully current with important learnings, decisions, and context from the session so
a future session can resume the task without losing important details. Do not include the current
uncommitted-file state, since it will likely change immediately after the handoff.

Finally, print a short copy-ready resume prompt for continuing from the handoff in a clean session.
Do not use block-quote or similar formatting that prefixes every line and hinders copy-paste.
