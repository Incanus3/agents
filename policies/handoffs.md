# Handoff Policy

This policy owns workstream handoff content, preservation and retirement. The handoff skill
provides execution mechanics and does not waive these requirements. Repository guidance owns
project-specific documentation roles, navigation indexes and archive placement.

## Maintain concise continuation, not a second source of truth

Keep one short-lived handoff per workstream under `docs/handoffs/`, using the workstream slug as
its identity. Maintain the repository's handoff index and links when a handoff changes or retires.
Update it at meaningful continuation checkpoints, not for routine narration or every small edit.

Include the implemented baseline, exact remaining gap and blockers, validated tracker references,
decisions and product constraints shaping the next increment, and recent verification evidence
only when it establishes the baseline or explains a blocker. State the next concrete action and
preserve the complete agreed remaining sequence, dependencies, pending decisions and authorization
or verification gates, either directly or through a canonical linked document.

Harvest lasting findings into their canonical specifications, product documents, guides or tracker
records before writing continuation state. Link those owners rather than copying specifications,
implementation plans, broad history or tracker contents into the handoff. Resolve Task references
under the [task-tracking policy](task-tracking.md#resolve-task-references-without-publishing-local-configuration),
including source-marker validation and publication privacy. Historical tracker IDs are provenance,
not authority to revive an archived delivery queue.

Exclude project-wide development, tooling, model, version-control, work-tracking and setup
instructions; those belong in the appropriate global policy, project guidance or guide. Exclude
speculative backlog, stale completed instructions, generic workflow checklists, secrets and
machine-specific operational inventories. Operator-agreed unfinished work is not speculative backlog.
Relevant environment cautions may remain only when they materially affect continuation and respect
publication/privacy requirements.

## Preserve commitments and gates when refreshing or shortening

Update the current position and retire completed instructions without dropping unfinished
commitments. Keep agreed steps even beyond the immediate next increment, including their
prerequisites and gates. When shortening, compress each unfinished step rather than omitting it.

Before removing or materially shortening information, verify that it is completed, explicitly
superseded, or preserved in a linked canonical owner. Repository history alone is insufficient.
Review the handoff diff before finishing: account for every removed commitment or gate and verify
that the complete remaining sequence is still discoverable.

## Retain workstream rulings until explicitly acknowledged

Keep every agent ruling for an active workstream in a dedicated section of its handoff, in decision
order, including rulings from completed tasks. A ruling resolves conflicting guidance, an ambiguity,
a plan defect, a review disagreement, or a scope/ownership trade-off. Routine progress is not a ruling.

For each ruling, record the decision, rationale, current status, and cost or risk if wrong; link its
canonical contract when useful. Preserve superseded or reversed rulings with their rationale and
identify their replacements rather than deleting them. Persist rulings before deleting temporary
ledgers or other execution artifacts. Chat, repository history and a current specification do not
replace the active ruling record.

Before retirement, present every ruling made autonomously during implementation and obtain the
operator's explicit acknowledgement, revision or rejection. Keep acknowledgement pending until
unambiguous. Workstream completion does not implicitly acknowledge rulings; one response may satisfy
both gates only when it expressly addresses both.

## Retire only after completion, acknowledgement and durable harvesting

Retirement requires all of the following:

- The operator explicitly confirms workstream completion.
- Every autonomous implementation ruling has received the explicit operator response above.
- Lasting decisions, evidence and instructions have been harvested into their canonical owners,
  and no agreed continuation remains unresolved.

Passed checks, completed plan steps, closed Tasks, commits, pushes, merges and deployments do not
substitute for these gates. Until they are met, preserve the baseline, remaining steps/gates or
pending decision about what comes next. Resolve a claimed completion that conflicts with known
unfinished commitments rather than silently dropping those commitments.

Where the workstream will merge, retire the handoff before merge once all gates are satisfied;
do not leave retirement as post-merge cleanup. Normally remove obsolete continuation. Archive only
material with a concrete continuing historical use, following repository placement/index rules;
do not permanently archive the entire ruling ledger merely to keep everything.

## Keep session-boundary and publication authority separate

Automatic maintenance alone does not require a new session or a resume-command announcement.
The global approved-design/plan clean-session rule is a separate trigger and still applies.
Explicit handoff requests and context-pressure transfers follow the handoff skill's resume-command
workflow. Handoff maintenance does not authorize implementation, commits, pushes, merges or other
external actions by itself; retain authorization already granted in the session or applicable policy.
