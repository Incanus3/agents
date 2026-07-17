---
name: ensure-no-behavior-changes
description: Verify that current code changes preserve behavior, without considering ABI compatibility. Use when asked for a behavior-preservation review.
---

Make sure all user changes preserve behavior. Do not consider ABI compatibility, and assume there
are no external, out-of-repository consumers of this code.
