---
name: jj-commit-and-push
description: Commit current Jujutsu changes and advance and push the active bookmark. Use when asked to commit and push with jj.
---

Given the current changes from `jj diff` and the session context, commit them with `jj commit` using
a meaningful header and a short summary of the relevant changes. Ignore simple reformats and
bookkeeping changes such as beads when describing the changes, unless creating beads for a plan or
PRD was the main work. Then advance the bookmark with `jj bookmark advance` and push it with
`jj git push`.
