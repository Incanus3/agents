---
name: feature-status
description: Assess the current feature's status from branch documentation and beads, then identify next steps. Manual invocation only: apply only if the user explicitly invokes `$feature-status`; never select automatically from a natural-language request.
---

Inspect documentation created in this branch with `jj diff -f master --name-only | grep ^docs` and
related beads. Report the current feature status and its next steps.
