---
name: test-and-refactor
description: Add characterization-style tests before refactoring to reduce complexity and method length. Use when asked to test then refactor code.
---

Cover this code with behavior-locking tests, then refactor it to reduce complexity and method length.
If the code is on the backend, don't consider frontend tests as coverage. Do not use classical TDD:
the tests should be green before the refactor, not red.
