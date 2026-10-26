# Task Tracking Policy

This policy governs tracker selection, task creation and organization, and lifecycle authority
for agentic work. Execution and external-action approval gates remain in effect independently
of task status.

## Select the repository task tracker

Inspect `taskman repo show --json` from the repository before tracking work. A valid registered
host/Project binding selects Taskman for repository planning, execution, dependencies and evidence.
Linked worktrees inherit their clone's binding. Adopting Taskman for an unbound repository requires
explicit operator registration before writing that repository's work to Taskman.
This selection supersedes older repository or skill tracker-selection instructions to use Beads,
including stale instructions in linked worktrees. The presence of `.beads/` does not select it over
a valid registration. Follow the Taskman CLI skill.
Keep endpoint names, Project IDs and credentials in local configuration rather than repository guidance.

An explicitly unbound repository retains its existing tracker; a configured default host alone does
not register a repository. A failed lookup, malformed/dangling binding, missing CLI, authentication
failure or unavailable backend is not an unbound result: stop affected tracker operations, report
the problem, and never fall back to a second writable queue. Do not unbind or override the selected
backend merely to bypass a failure. If a migrated clone still contains a Beads archive, keep that
existing archive private, untracked, ignored and read-only; use it for historical references only
unless the operator explicitly authorizes archive maintenance. An archive need not exist: do not
create or copy one into a new checkout solely to satisfy these rules.

An explicit assignment to a nonterminal Taskman Task authorizes bounded updates within its agreed
scope, evidence comments, and transitions to In Progress or In Review. Read the Task/thread and
blockers first; verify mutations. Assignment does not authorize new scope or priority, reopening
terminal work, Done outside the child-review completion rule below, Will Not Do,
unresolved-blocker overrides, deletion or consequential external actions. Those require explicit
operator decisions. Registration, discovery, runtime activity and passed checks alone grant no
execution or completion authority. In Progress is not an atomic claim;
coordinate ownership before concurrent work. Broader commitments still require operator authorization.

## Create workstream tasks after plan approval

Create new tracker tasks for a feature or other workstream only after the operator approves its
implementation plan. During design and plan review, keep the proposed task breakdown in the plan.
Create Taskman Tasks arising from implementation-plan approval in Pending, including newly created
workstream roots, intermediate parents, and implementation children. Design approval alone does
not authorize creating tracker tasks; using a non-execution status does not bypass this gate.

When decomposing a workstream into more than one task, group those tasks under a common parent task
for that workstream. After plan approval, inspect and reuse an appropriate existing parent or create
one, then create the implementation tasks as its children. Dependency links may order the children
but do not replace parent-child grouping. A workstream requiring only one implementation task does
not need an additional parent solely for grouping.

## Move existing Tasks to Pending after design approval

When the operator approves the design for an existing Taskman Task that is in Icebox, move that
Task to Pending. Pending means the work has an approved design and is awaiting further planning
or implementation; it does not mean its implementation plan has already been approved.

Design approval authorizes this bounded status transition, but does not authorize implementation
or creation of new tracker tasks. Implementation still requires an approved implementation plan
and the applicable execution/session gates. Do not reset Tasks already In Progress, In Review,
Done, or Will Not Do merely because design approval is recorded.

## Start picked-up Tasks and Pending ancestors together

When an implementor picks up an assigned Pending Task after the applicable implementation-plan,
execution, ownership, and blocker checks, move that Task to In Progress. Walk its ancestor chain
and move every ancestor still Pending to In Progress as well, so activity propagates through
intermediate parents to the workstream root and any further Pending ancestors.

Change only Pending ancestors. In particular, do not reset ancestors already In Review during
human-review corrections, or reopen Done or Will Not Do ancestors through this propagation.
Picking up review fixups leaves the child In Review under the review-loop rule below.

## Distinguish the workstream root from intermediate parents

The workstream root is the Task representing the overall approved workstream, or its standalone
Task when no decomposition is needed. Intermediate parents are child Tasks within that workstream
which themselves have children. Identify the root from the approved scope and hierarchy; having
children does not by itself make every intermediate parent a human-acceptance gate.

An intermediate parent's required child work must be complete before its own independent review
can accept the parent. Move the intermediate parent to In Review for that review, keep it there
through fixups and re-review, and move it to Done upon independent reviewer acceptance of its full
scope. The same child-completion authority applies at each depth below the workstream root.

When all required children of the workstream root are complete and its implementation is ready
for final acceptance, move the root to In Review for the managing human. Only explicit human
acceptance authorizes moving that root, or a standalone workstream Task, to Done. Child-review
acceptance does not imply acceptance of the overall workstream.

## Keep child review and fixups in In Review

When an implemented child Task is handed to an independent reviewer, move it to In Review.
Keep it In Review throughout reviewer feedback, implementor fixups, and subsequent review rounds.
Do not alternate between In Progress and In Review for these handoffs: fixups are part of review.
The workstream root remains In Progress during initial child implementation and review.
Human-review corrections follow the rules below instead of resetting the root to In Progress.

When the independent reviewer explicitly accepts the final result with no unresolved findings,
move that child Task to Done. This is standing operator authorization for bounded child-task
completion within the approved workstream; separate human approval of each child is not required.
Record the review result and verification evidence before closing the child and verify the
transition. The reviewer must be independent of implementation and fixups, as defined by the
[delegation policy](delegation.md#separate-implementation-from-verification).

This exception does not authorize unresolved-blocker overrides, completion of the workstream
root or a standalone Task, or reopening terminal Tasks. Those decisions still require explicit
operator authorization. Passing tests or an implementor's own acceptance does not substitute for
independent reviewer acceptance.

## Track human-review corrections proportionately

During human review of the workstream root, small corrections may be handled without new tasks
or status changes. Comments on the appropriate parent or child Task are optional when they help
preserve useful context or evidence; do not reopen Done children merely to account for minor fixups.

For larger corrections within an existing child Task's scope, the operator may choose to reopen
that child from Done to In Review. That decision authorizes this specific reopening. Keep the child
In Review through fixes and independent re-review, then apply the child-review completion rule.

If the request introduces additional scope, the operator may choose a new child Task instead.
Obtain approval for that scope and follow the existing plan-approval, task-creation, grouping, and
List-placement rules. Review feedback does not grant blanket authority to expand the workstream.

The workstream root remains In Review while its human-review corrections are addressed unless
the operator directs otherwise. Use the operator's assessment of correction size and scope; when
the appropriate tracking treatment is unclear, clarify it rather than inventing numeric thresholds.

## Choose task locations from the List hierarchy

Before creating Taskman Tasks, retrieve the complete List hierarchy for the target Project and
inspect the existing Lists' names, locations, and available descriptions. Choose the best matching
existing List for the work rather than defaulting to the Project root. Apply this placement check
to workstream parent Tasks and their children; Task parentage does not determine List ownership.

If no existing List is a good match, propose a new List's name and exact location: either the
Project root or the full path of its intended parent List. Explain briefly why that placement fits
and obtain operator approval before creating the List or the Tasks that would belong to it. Do not
silently create a List or use the Project root as a fallback.

## Resolve Task references without publishing local configuration

A full Task identity includes the registered host, Project ID and Task ID. Preserve an explicitly
qualified reference's own context; titles or arbitrary bare IDs do not establish identity.

Public repository documents may instead record a Task ID relative to their owning repository's
registered Project, together with the exact repository-qualified `Source: ...` description marker.
Resolve host and Project through the current valid binding, inspect that exact Task in that Project,
and verify its recorded marker before accepting the reference. Report the resolved full identity
to the operator without persisting operator-local host/Project settings in public repository files.
New Tasks may use documented source markers for their repository/workstream; Beads provenance is
not required. Preserve an existing migrated source marker when one is part of the reference.

A missing binding or missing/mismatched marker leaves the reference unresolved. Report it and stop
dependent work; do not guess by title, query another host/Project, or resume an archived tracker.
Cross-Project references require an explicitly qualified identity and must not silently inherit
the current repository's context.

## Manage Beads through br

This section applies only when Beads is the selected writable tracker or the operator explicitly
authorized archive maintenance. It does not authorize writes to a retained read-only archive;
report unexpected archive edits rather than automatically reconciling or synchronizing them.

Use `br` for all Beads issue and synchronization mutations. Never edit `.beads/issues.jsonl`, `.beads/*.db`, or related
state files directly; treat the JSONL file as an exported version-control artifact. If a direct or external edit is
discovered, reconcile the state through `br` and verify the affected issue with `br show` and the workspace with
`br sync --status`.

