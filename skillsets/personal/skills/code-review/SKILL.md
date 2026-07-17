---
name: code-review
description: Thoroughly review current branch changes for defects, omissions, security issues, tests, and maintainability. Use when asked to review code changes.
---

Go through the changes in this branch and review them thoroughly. Use the relevant skills for this.
Look for:

- Potential bugs and inconsistencies.
- Unfinished work: missing feature pieces, unhandled edge cases, missing test coverage, and TODO or
  FIXME comments.
- Security issues.
- Optimization opportunities that do not unreasonably increase complexity or reduce readability and
  maintainability.
- Simplification opportunities that preserve functionality, correctness, and efficiency.

Before starting, inspect documentation created in this branch with
`jj diff -f master --name-only | grep ^docs` to gather the relevant context.

If the branch is sizable, use parallel subagents intelligently to avoid running out of context.
Avoiding compaction during a review is important because losing context can lead to incorrect
findings and reasoning.
