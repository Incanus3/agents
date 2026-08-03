# Global Agent Conventions

These rules capture general practices that should carry across projects and sessions.

## Use tool-neutral documentation paths

Store design artifacts in stable, purpose-based directories:

- Specifications: `docs/specs/`
- Implementation plans: `docs/plans/`
- Session handoffs: `docs/handoffs/`

Do not put workflow, skill collection, or tool names such as `superpowers` in documentation directory names unless the
documents are specifically about that tool. Tool-neutral paths remain accurate when workflows or agents change.

## Keep durable documentation tool-neutral

Write repository documentation in portable Markdown. Do not embed agent UI tags, tool-call markup, rendering wrappers,
or other tool-specific syntax in specifications, implementation plans, handoffs, or user-facing documentation. Such
markup is for chat presentation only.

## Make specifications self-contained handoff artifacts

A fresh session should be able to plan and implement from a specification without relying on prior conversation history.
Include the context needed to resume safely:

- Relevant repository and environment state
- External research, observed behavior, and source links
- Requirements and explicit decisions
- Rejected alternatives and accepted trade-offs
- Exact command, API, and error semantics
- Expected file boundaries and responsibilities
- Testing and verification strategy
- Known caveats and a next-session checklist

Before finalizing a specification, remove placeholders and resolve contradictions or ambiguous requirements.

## Read design context before executing plans

Before implementing from a plan, read the complete design specification referenced by that plan. Use the design to
understand scope, safety constraints, and accepted decisions; do not rely on the plan alone when it summarizes them.

## Navigate project knowledge deliberately

Start with the project's navigation entry point, index, or equivalent repository map when one is available. Follow only
the references relevant to the task; do not load an entire knowledge base or documentation tree by default.

## Preserve durable knowledge and document authority

Capture meaningful findings, decisions, research progress, workflow changes, and verification evidence in their
canonical project artifacts rather than copying conversation transcripts. Prefer updating an existing source of truth
over creating a competing document.

When guidance is replaced, mark the older guidance as superseded and retain important rationale in the appropriate
decision record. When a repository maintains curated content indexes, update the relevant index when its contents or
children change.

## Curate durable knowledge rather than accumulate records

Persist conclusions, evidence, useful provenance, and actionable follow-up context. Do not preserve routine progress
narration, duplicated command output, ungrounded speculation, or complete conversation transcripts as durable project
knowledge.

When a detail does not affect future decisions, behavior, authority, verification, or resumption, omit it from
canonical documentation.

## Apply proportionate rigor and maintain human control

Treat work that creates or changes durable artifacts, decisions, task state, or multi-step work as **material**. Treat
work that can cause meaningful rework, external effects, security or data risk, or a change to canonical practice as
**consequential**. Apply documentation and verification rigor proportionately.

Keep the operator in control of priorities, scope expansion, irreversible or external actions, and the promotion of
experimental practice into canonical guidance. Escalate uncertainty that materially changes intent, risk, or blast
radius rather than silently choosing on the operator's behalf.

## Separate technical readiness from authorization

Completion, verification, committing, pushing, or other evidence of technical readiness does not authorize a
consequential action. Require explicit operator authorization before merging, deploying, publishing, altering shared or
external state, deleting material resources, or otherwise taking an irreversible action, unless an accepted project
policy explicitly grants that authority.

Before publishing or landing work, refresh the relevant target and remote state. Do not revive a stale branch, target,
review, or other shared reference merely because it remains locally visible.

## Match verification to the risk

Use self-checks for trivial, local, reversible edits; fresh-context review when author bias or discoverability matters;
independent specialist review for security, correctness, architecture, or domain risk; and human acceptance for intent,
priority, material risk, and external consequences.

Automated checks complement rather than replace judgment. A verifier should inspect the artifact directly, reproduce
checks where feasible, map evidence to acceptance criteria, and state material uncertainty.

Do not expand normal implementation and verification work into a full-branch review. Verify the work implemented in
the current session and how it interacts with relevant existing code. Perform a full-branch review only when the
operator explicitly requests one.

When a task intentionally adds red tests, contract tests, fixtures, or scaffolding before later implementation, verify
the tests and helpers against that task's stated scope. Treat failures explained by deferred implementation as expected;
investigate only accidental regressions, broken scaffolding, or failures that contradict the scope. Do not broaden the
task into implementation or unrelated test cleanup without approval.

## Improve repeated failures with the smallest durable intervention

When a material failure or avoidable interruption recurs, identify its cause before changing the process. Prefer the
smallest durable intervention that addresses the demonstrated problem: a clear rule, checklist, example, test, or
template before a new tool or service.

Retain the intervention only when evidence shows a net improvement. Do not create lasting process or tooling for a
one-off problem without a clear reason to expect recurrence.

## Apply the delegation policy

Before deciding whether to delegate work, selecting a delegated-agent model, or coordinating parallel agents, read
`~/.agents/policies/delegation.md` completely and apply it. Tool-specific skills govern execution mechanics but do not
replace this policy.

## Keep planning terminology out of product surfaces

Production code, test names, user-facing documentation, command output, and APIs must remain independent of internal
phases, beads, tickets, milestones, or implementation sequence. Describe behavior and capability instead.

Planning identifiers belong in trackers, implementation plans, and handoffs. Before completing work, search
implementation-facing files for leaked planning terminology and replace it with durable domain language.

## Browser workflows in Orca

When working inside Orca, prefer its embedded `orca-ide` browser for browser inspection and interaction.

## Inventory all persistent state before designing indirection

Before introducing profiles, switching, aliases, or symlink-based indirection, identify all state used by the underlying
tool. Inspect visible data directories as well as lockfiles, metadata, caches, links, and state-directory environment
variables.

Keep related data and metadata together. Switching visible files without their associated metadata can leave management
commands operating on a different logical state than the files currently in use.

## Close material work with durable state and evidence

Before declaring material work complete, persist meaningful findings, decisions, and evidence in their canonical
owners; update affected indexes or references; and record bounded follow-up work with enough context to resume.

Record the verification performed and unresolved uncertainty. Use the handoff skill to maintain short-lived resume
state at meaningful continuation checkpoints and to retire it when work completes. Summarize the outcome rather than
the conversation.

## Prefer repository-aware version-control tooling

Before the first version-control operation, run `but status --json` when `but` is available. If `but` is
initialized in the workspace, use `but` for version-control operations; use raw Git only when `but` cannot perform the
required action. Never run `jj` in a `but` workspace.

If `but` is not initialized and the workspace contains `.jj/`, use Jujutsu for all version-control operations and do
not run raw Git. Otherwise, use raw Git as the fallback.

When a diff contains unexpected changes, do not revert them automatically. Treat them as potentially intentional; if
they should not be included in the current change, ask the requester before modifying or excluding them.

## Stop on stale Jujutsu working-copy state

If a Jujutsu command reports that the working copy is stale, stop immediately. Do not retry the command, refresh the
working copy, or attempt a workaround; report the condition to the requester and wait for them to resolve it.

## Treat rewriting pushed Jujutsu history as exceptional

Only bypass immutable-commit protection when the user explicitly requests rewriting pushed history. Do not weaken the
repository's immutable-head configuration for a one-off rewrite.

When a rewrite is authorized:

1. Use the command-scoped `--ignore-immutable` override.
2. Push through Jujutsu with the intended bookmark explicitly selected.
3. Verify that the local and remote commit IDs match after the push.
