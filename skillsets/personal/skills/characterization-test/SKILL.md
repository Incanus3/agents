---
name: characterization-test
description: Add durable characterization-style test coverage before a refactor. Manual invocation only: apply only if the user explicitly invokes `$characterization-test`; never select automatically from a natural-language request.
---

Make sure this code has very good test coverage, so that I can confidently refactor it.
Add missing test coverage where needed. The added tests should lock in the current behavior and have
good line/branch coverage, but they should be structured as standard long-lived tests, not as
temporary tests created just for the refactoring and dropped afterwards. Their name should not
contain the term "characterization" unless it is part of the tested code's name, since that label
is temporal and not relevant long-term.

If this code is on the backend, don't consider frontend tests as coverage.
