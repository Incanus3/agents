---
name: jj-commit
description: Commit current Jujutsu changes with a meaningful header and concise summary. Use when asked to commit with jj.
---

Given the current changes from `jj diff` and the session context, commit them with `jj commit` using
a meaningful header and a short summary of the relevant changes. Ignore simple reformats and
bookkeeping changes such as beads when describing the changes, unless creating beads for a plan or
PRD was the main work.
