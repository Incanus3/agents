# Obra, Osmani, and Pocock Skillsets

## Executive summary

- **Obra** is a strict, process-enforcing software-development workflow.
- **Osmani** is a broad, production-oriented engineering handbook.
- **Pocock** is an interactive product-shaping, architecture, and multi-session workflow toolkit.

A useful shorthand:

> Pocock helps decide what to build. Obra tightly controls how it gets built. Osmani covers the widest range of
> engineering concerns.

## Main differences

| Dimension | Obra | Osmani | Pocock |
| --- | --- | --- | --- |
| Primary emphasis | Disciplined execution | Complete engineering lifecycle | Discovery, design, architecture, and coordination |
| Structure | One opinionated workflow | Skills organized by engineering phase | Main flow plus on-ramps and standalone tools |
| Interaction style | Mandatory gates and checklists | Structured senior-engineering guidance | Conversational, user-driven commands |
| Invocation | Strongly automatic | Automatic phase-based routing | Often explicit; 22 of 40 skills disable model invocation |
| Implementation | Detailed plans, TDD, subagents, and reviews | Thin slices plus production concerns | Lightweight `implement` coordinating TDD and review |
| Distinctive strength | Predictability and verification | Breadth and operational completeness | Product thinking, domain language, deep modules, and huge-work planning |
| Main overhead | Ceremony, frequent gates, and many reviews | Large amount of guidance and context | Tracker/setup assumptions and human interaction |
| Current size | 15 skills, about 3,464 lines | 25 skills, about 7,094 lines | 40 skills, about 2,891 lines |

### Obra: strict engineering rails

Obra's `using-superpowers` skill establishes a forceful rule: check and invoke relevant skills before doing anything. Its
workflow is approximately:

1. Brainstorm and obtain design approval.
2. Write a detailed plan.
3. Work in an isolated workspace.
4. Implement through TDD.
5. Review every task.
6. Run a final review and fresh verification.
7. Finish the branch through a controlled integration process.

Its TDD skill has an explicit "no production code without a failing test first" rule. Its subagent workflow uses a fresh
implementer and reviewer for each task, durable progress files, and another whole-branch review.

**Character:** Prescriptive, safety-first, and hard to accidentally bypass.

**Trade-off:** Even simple changes can trigger design approval, documentation, planning, TDD, and review ceremony. It
also assumes Git-oriented branch and worktree workflows in several places.

### Osmani: broad engineering coverage

Osmani is organized around the complete development lifecycle:

- requirements interviewing and idea refinement
- specification and task breakdown
- context and source-driven development
- incremental implementation and TDD
- frontend and API design
- browser testing and debugging
- security, performance, and observability
- CI/CD, migrations, and deprecations
- documentation, ADRs, launch, and rollback

Its global posture emphasizes surfacing assumptions, stopping on confusion, pushing back, simplicity, scope discipline,
and evidence-based completion.

A distinctive skill is `doubt-driven-development`: important decisions receive an adversarial fresh-context review while
implementation is still underway. Obra performs strong reviews too, but Osmani explicitly treats adversarial doubt as an
in-flight engineering technique.

**Character:** Comprehensive, production-conscious, and close to a senior-engineering playbook.

**Trade-off:** It is the largest collection and may load more process than routine tasks need. Its skills sometimes
prescribe artifact locations such as `tasks/plan.md`, so repository conventions may need to override those defaults.

### Pocock: shaping, domain design, and context management

Pocock defines an explicit idea-to-ship flow:

1. Use `grill-with-docs` to sharpen the idea.
2. Use `prototype` when conversation cannot answer a design question.
3. For multi-session work, create a specification and tracer-bullet tickets.
4. Start each ticket in fresh context with `implement`.
5. Implement through TDD and finish with a two-axis code review.

Its most distinctive capabilities are:

- relentless one-question-at-a-time interviewing
- persistent domain vocabulary and ADRs
- deep-module and seam-based architecture
- alternative interface design through parallel agents
- throwaway prototypes and explicit context handoffs
- `wayfinder` for work too large or uncertain to plan in one session
- issue triage and tracker-centered coordination

Its TDD approach is also distinct: agree on public testing seams with the user first, then test behavior through those
seams. Refactoring is deferred to review rather than included in the red-green loop.

The collection also contains niche tools for writing, Obsidian management, course exercise scaffolding, TypeScript module
setup, and interactive setup wizards. Its count of 40 skills therefore does not mean it offers broader general engineering
coverage than Osmani.

**Character:** Collaborative, conceptual, architecture-aware, and optimized for maintaining clarity across long efforts.

**Trade-off:** Many important flows require explicit invocation, user participation, and issue-tracker setup. Its actual
`implement` skill is a small coordinator; the collection's differentiation lies mostly before and around implementation.

## When to use each skillset

### Use Obra when

- Requirements are sufficiently clear and disciplined execution is the priority.
- The agent tends to jump into code or prematurely declare success.
- Test-first development and independent review are important.
- Work can be divided into well-specified tasks.
- Extra ceremony is cheaper than defects.

Good examples include implementing an established feature specification, fixing correctness-sensitive bugs, refactoring
behavior under tests, and executing a multi-task plan with subagents.

Avoid it for rapid experimentation, tiny low-risk changes, or work that frequently departs from its prescribed workflow.

### Use Osmani when

- One general-purpose default skillset is wanted.
- Work spans more than implementation alone.
- Production concerns include security, performance, observability, migration, or deployment.
- Unfamiliar libraries require official-source verification.
- High-risk decisions would benefit from adversarial review.
- Domain-specific guidance such as accessibility, API design, browser inspection, or CI/CD is needed.

Good examples include production web applications, full-stack features, public API changes, authentication, performance
investigations, staged rollouts, deprecations, and unfamiliar frameworks.

This is the best single default of the three when broad engineering coverage is the priority.

### Use Pocock when

- The main uncertainty is what should be built rather than how to code it.
- A human-led design interview is useful.
- Domain terminology is fuzzy or overloaded.
- Architecture and public module seams need careful design.
- A runnable prototype would answer questions better than discussion.
- Work spans multiple sessions and requires durable handoffs.
- A project is too large or foggy for a normal up-front plan.
- Incoming issues need triage before implementation.

Good examples include early-stage feature exploration, greenfield architecture, alternative interface design, difficult
domain models, major tracker-backed investigations, architecture improvements, and conversational QA.

It is less compelling as the sole skillset for routine autonomous coding unless its named flows are actively invoked.

## Practical recommendation

When switching skillsets according to the work:

1. Start with **Pocock** for vague, consequential, or architecture-heavy ideas.
2. Switch to **Obra** once the specification is settled and tightly controlled execution is wanted.
3. Use **Osmani** as the everyday default or when production concerns extend beyond the Obra and Pocock core flows.

When choosing only one:

- Choose **Obra** for maximum discipline.
- Choose **Osmani** for maximum engineering breadth.
- Choose **Pocock** for maximum collaboration, shaping, and architectural clarity.
