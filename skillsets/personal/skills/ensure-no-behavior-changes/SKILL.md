---
name: ensure-no-behavior-changes
description: Verify that current code changes preserve behavior, without considering ABI compatibility. Manual invocation only: apply only if the user explicitly invokes `$ensure-no-behavior-changes`; never select automatically from a natural-language request.
---

Make sure all user changes preserve behavior. Do not consider ABI compatibility, and assume there
are no external, out-of-repository consumers of this code.
