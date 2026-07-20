---
name: find-extraction-candidate
description: Identify the best cohesive responsibility to extract during a refactor. Manual invocation only: apply only if the user explicitly invokes `$find-extraction-candidate`; never select automatically from a natural-language request.
---

I want to refactor this code by extracting one cohesive responsibility into a smaller collaborator.

Inspect the target code and enough surrounding context to make a safe recommendation:

- Nearby interfaces and abstract classes.
- Subclasses and overrides.
- Direct callers when relevant.
- Existing tests.
- Existing local abstractions and utilities.

Do not implement anything yet. Identify the best extraction candidate. The goal is not to hide the
ugliest code; it is to find a cohesive responsibility that is orthogonal to the target's main job,
currently owned mostly by accident or convenience, has a clear domain or policy boundary, can be
meaningfully named and independently tested, and can be extracted without convoluted dependencies.

Pay special attention to dependency direction. Prefer a current component delegating one specific
responsibility to the extraction. In special cases, the extracted component may wrap the current
one. Avoid mutual callbacks, shared mutable state, broad constructor or API churn, heavy subclass
changes, and cyclic dependencies.

Evaluate candidates for cohesion, orthogonality, dependency shape, testability, subclass and caller
impact, behavior-preservation risk, and simplification value.

Return:

1. A short summary of the target's apparent main responsibility.
2. Two to four possible extraction candidates.
3. For each candidate: proposed name, owned responsibility, required inputs and dependencies,
   delegation shape, fit assessment, expected test strategy, and risk level.
4. The recommended first extraction.
5. Why it is the best first step.
6. Stop after the recommendation. Do not modify code until explicitly asked.
