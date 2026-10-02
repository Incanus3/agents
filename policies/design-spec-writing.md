# Design Specification Writing Policy

## Purpose and scope

Apply this policy when writing, revising, or preparing design specifications for operator review before implementation
planning. Optimize how quickly the operator can understand and judge the decisions without sacrificing completeness,
accuracy, or human control.

Keep specifications self-contained as required by `AGENTS.md`. An overview or decision inventory is a navigation aid,
not a substitute for the full design. Do not omit, hide, or demote details merely because the agent judges them
unimportant. Scale the structure to the design; do not add empty sections or unnecessary process artifacts.

## Structure for reading and judgment

- Prefer short sections, structured lists, and comparison or scenario tables over long unstructured prose.
- Use meaningful headings that identify the behavior or decision. Prefer “Retries stop after five attempts” to
  “Retry strategy” when the section establishes that contract.
- Put conclusions and requirements before supporting explanation. Keep related evidence, rationale, and consequences
  close to the claim or decision they support.
- Remove glue text, repeated summaries, generic introductions, promotional language, and narration of the design
  process. Retain reasoning that affects a decision or explains a constraint.
- Preserve whitespace and readable sentences. Information density is useful information per unit of attention, not
  the fewest possible lines or words.
- Choose the format that fits the information: tables for comparison, lists for parallel items or steps, short prose
  for causal reasoning, and diagrams for relationships and flows. Avoid wide tables, deeply nested lists, excessive shorthand,
  and forcing every explanation into bullets.

## Provide a decision inventory

Near the beginning, list every design decision with a stable identifier, status immediately after the identifier,
proposal or inherited choice, concrete downside, and link to its rationale. Do not present recommendations as already
accepted.

| ID | Status | Decision or proposal | Downside or constraint | Rationale |
|---|---|---|---|---|
| D1 | Proposed | Stop retries after five attempts | Transient failures can still exhaust retries | Link to decision section |

Group rows by status in the order below. Within each status group, sort rows by identifier; ID ordering applies only
inside that group, never across the whole table. Restore this ordering whenever rows are added or their status changes:

1. **Unresolved:** a choice is needed but no recommendation is ready.
2. **Proposed:** a recommendation awaits operator approval.
3. **Accepted:** the operator has approved the decision.
4. **Rejected:** a proposal was declined rather than accepted.
5. **Superseded:** a previously accepted decision was replaced; link to its replacement.

These are display groups, not a mandatory sequence every decision must traverse. Treat inherited as provenance rather
than a separate status; record the source and its established acceptance. Use natural identifier ordering (for example,
D2 before D10), and preserve identifiers when sorting rather than renumbering decisions.

The row above illustrates the format, not a required retry policy. Populate inventories with actual decisions and
working links. Include inherited decisions and their authoritative sources, especially where they constrain the new
design. Keep unresolved choices visible rather than silently selecting an option.

## Use a consistent decision structure

For each decision, make the following information easy to find:

1. **Context and constraints:** the problem, requirements, and forces shaping the choice.
2. **Credible alternatives:** feasible options compared on the same relevant dimensions.
3. **Recommendation:** the proposed choice and its rationale, including where it loses to an alternative.
4. **Consequences:** benefits and concrete costs, including complexity, operational burden, compatibility effects,
   failure modes, recovery limitations, and reversibility where applicable.
5. **Revisit conditions:** evidence or changed constraints that would justify reconsidering the decision.

Use compact entries for simple decisions and more explanation where necessary. Do not invent alternatives or trade-offs
to fill a template. State when constraints leave only one feasible option. Avoid vague costs such as “some additional
complexity”; identify the added component, responsibility, dependency, or behavior.

## Separate evidence from judgment

Clearly distinguish these categories wherever confusing them would affect review:

| Category | Meaning | Required supporting context |
|---|---|---|
| Observed fact | Behavior or constraint established by inspection or research | Relevant source, command, environment, or verification evidence |
| Requirement | Behavior or constraint the design must satisfy | Origin or authority |
| Assumption | A premise that has not been established | Basis, uncertainty, and what changes if it is false |
| Proposal | A choice awaiting approval | Rationale, consequences, and decision status |

Attach evidence beside the claim it supports. Prefer “verified using this command in this environment” over unsupported
confidence labels. Distinguish source statements from inferences. Identify uncertainty that materially affects intent,
risk, feasibility, or blast radius; do not disguise it as a settled requirement.

## Show behavior with concrete scenarios

Present observable behavior before implementation mechanics. Use concise examples or scenario tables covering normal
operation, boundary cases, and failures. Include exact inputs, outputs, errors, and state changes where they define the
contract. Specify what survives a failed operation and how recovery works when relevant.

Prefer “When the destination exists, return the specified error and leave both files unchanged” to “Handle existing
destinations safely.” Examples clarify requirements but do not replace the complete contract; explain their scope and
keep them consistent with the normative requirements.

## Use Mermaid where relationships benefit from a diagram

Use Mermaid when a diagram makes a complex flow or relationship easier to inspect, especially:

- Flows with more than one or two conditions, loops, retries, or recovery paths.
- Interactions among several components or participants.
- Nontrivial dependency, ownership, or hierarchy relationships.

Choose the diagram type for the question: flowchart for branching, sequence diagram for interactions, state diagram
for lifecycle transitions, or graph for dependencies and hierarchy. Label conditions, loop exits, failure paths, and
edge meanings where relevant. Split diagrams that become too dense to read.

Keep diagrams consistent with the written contract and update both when behavior changes. Do not make readers infer
exact API or error semantics from a diagram alone. Avoid decorative diagrams for a single fact or a simple sequence
already clear in text.

## Make revisions reviewable

- Preserve stable section and decision identifiers so comments and links remain useful.
- After review-driven revisions, provide a concise change register identifying what changed, why, and which decisions
  or prior approvals are affected. Link to the changed sections.
- Avoid gratuitous rewriting, renumbering, or reordering that forces a full reread.
- Mark replaced decisions as superseded and preserve useful rationale in the canonical decision record. Keep the
  current specification authoritative; do not maintain conflicting versions of the design.
- Do not silently carry approval across changes that invalidate its basis. Make the affected approval scope explicit.

## Prepare review evidence and explicit approval questions

Before presenting a specification, resolve verifiable questions within the authorized scope: inspect repository
behavior and API contracts, check sources, identify missing cases, and remove contradictions or ambiguities. Record
relevant verification evidence and remaining uncertainty. Do not leave avoidable investigation for the operator or
claim verification that has not been performed.

Agents can establish evidence and check consistency; these checks do not establish operator intent or acceptance of
trade-offs. End with explicit questions requiring operator judgment, linked to the corresponding decisions. Prefer
“Accept delayed failure detection in exchange for automatic recovery?” to “Does this design look good?” State what
approval would cover and preserve unresolved choices as unresolved. Silence is not approval, and technical readiness
does not authorize consequential actions.

## Background references

- [NN/g: Writing descriptive headlines and titles](https://www.nngroup.com/articles/microcontent-how-to-write-headlines-page-titles-and-subject-lines/)
  supports meaningful, keyword-first headings for scanning. Its research concerns web reading rather than design-spec
  review specifically.
- [Michael Nygard: Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
  describes decision records organized around context, decisions, status, and consequences.
