---
name: test-and-refactor
description: Add characterization-style tests before refactoring to reduce complexity and method length. Manual invocation only: apply only if the user explicitly invokes `$test-and-refactor`; never select automatically from a natural-language request.
---

Cover this code with behavior-locking tests, then refactor it to reduce complexity and method length.
If the code is on the backend, don't consider frontend tests as coverage. Do not use classical TDD:
the tests should be green before the refactor, not red.
