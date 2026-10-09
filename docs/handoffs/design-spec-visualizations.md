# Design specification visualizations

- Status: active
- Updated: 2026-10-06
- Resume: `$resume design-spec-visualizations`

## Objective and authorization

Make design review easier without losing self-contained requirements, costs, uncertainty or operator authority.
The operator approved revised C’s general form/organization and approved a personal design-visualization skill plus
a short extension of the existing writing policy. Creation, local installation and bounded forward tests are now
complete. The operator subsequently requested all changes committed and landed in both `.agents` and `skillsets`,
including earlier dirty skill updates. Publication of previews, native host actions and software implementation remain
outside that request. Retain this handoff until the operator explicitly confirms workstream completion.

## Current capability and canonical owners

- Writing policy: [design-spec-writing.md](../../policies/design-spec-writing.md), already referenced by AGENTS.md.
  Added “Add an HTML review companion when it improves understanding”: conditional use, skill routing, source
  authority, faithful statuses/boundaries, current versus stale snapshot, rendering checks and publication boundary.
- Personal skill: `/home/jakub/orca/projects/skillsets/personal/skills/design-visualization/SKILL.md`.
  Also accessible as `~/.agents/skillsets/personal/skills/design-visualization/SKILL.md` and under the globally
  Codex-enabled personal skill collection. Explicit invocation: `$design-visualization`; implicit selection enabled
  by default. Existing personal collection is manual. No integration links changed; no Claude collection is enabled.
- Skill resources: `assets/review.css`, `assets/shell.html`, `assets/reference.html` (generic fictional worked example),
  `references/visual-patterns.md`. Familiar dark styling/sidebar/component boundaries, technical headings and
  text-plus-color statuses; adaptable sections and central representation. Optional contained scrolling and labeled
  mobile-row patterns. Static default; significant costs/failures visible; faithful local source snapshots and links.
- Durable experimental assessment/evidence:
  `/home/jakub/.local/share/caddy-design-views/2026-10-03/comparison.md` and `skill-tests/verification.md`.

## Experiment artifacts and operator findings

Private/local artifact root: `/home/jakub/.local/share/caddy-design-views/2026-10-03/`.
Gallery: `http://127.0.0.1:41637/` (loopback-only local preview; exec session83561).
Orca embedded page0799ee02-1e32-41ae-b16f-1e780eb3eba2 belongs to primary; page can show gallery/trials.

Original variants A/B/C and `variant-c-revised/index.html` remain available. Revised C has C’s clear borders,
backgrounds/semantic stripes and sidebar, with direct technical headings instead of A/C’s promotional slogans and
metaphors. B had stronger technical wording and individually attributable decision costs, but blended components.
C’s explicit disk/runtime state comparison was the strongest visual explanation. All original views remain text-heavy.
No human review-speed measurement or general cross-design assurance is claimed.

Canonical Caddy source:
`/home/jakub/orca/workspaces/taskman/deploy-qwazar/docs/specs/2026-10-01-shared-caddy-design.md`.
Snapshot `source.md`, rendered `source.html` and provenance.json at artifact root. Snapshot SHA256:
`9d3e26984bcebccc74988b1a902a710b3e74522fe0821b944361c9db7ca60b5d`.
Snapshot includes accepted D23 configuration-preserving installation and deployment-host-local proof clarification.
Use current source if continuing Caddy work; do not assume this snapshot remains current. Proposed design approval,
native acceptance and implementation authority remain separate and pending in the source workstream.

Earlier writing-policy work is captured in canonical policy/history: structured high-density prose, diagrams for
relationships/flows, ID then Status with grouping and ID sort within group, distinct representation roles, choices
versus derived behavior, authoritative contracts/rationale and cross-section consolidation. Do not chase original
spec length. Karpathy post motivated the HTML experiment; strict ASD-STE100 was not adopted.

## Verification and bounded trial outcomes

Three original agents independently built A/B/C; primary checked content, screenshots and all source anchors
(A36/B33/C33 valid). Revised C kept CSS/component structure, source links and decision identifiers. Primary viewed
entry/activation, verified no desktop overflow and sticky sidebar, and persisted the operator’s preferred direction.

Capability implementation: primary owned skill/policy; viz_assets owned reusable assets. Independent fresh-context
viz_delivery_trial and viz_rotation_trial applied skill to fictional `skill-tests/delivery.md` and `rotation.md`:

- Delivery: participant exchanges plus retry/replay transitions. Preserves queued versus applied proof, lost-reply
  deduplication, quarantine retention and separately authorized same-ID replay. Exposes unspecified retry timing basis.
- Rotation: lifecycle state comparison plus four recovery panels. Preserves complete-inventory/consumer confirmation
  gate, revocation uncertainty and impossible rollback after confirmed revocation. No raw secrets or provider actions.
- Trials used shared presentation with different central explanations. Both correctly rejected unrelated/simple
  automatic HTML routing. Both reapplied source-anchor, inventory-format and mobile comparison refinements.
- Independent agents inspected desktop1440 and actual narrow390; no page overflow. Delivery checked scroll focus/
  hints and both sides; rotation checked stacked labels. Primary read complete outputs/notes, compared source
  boundaries, checked raw-source/CSS equality, all links, separate ID/Status and resource completeness, and viewed
  desktop/narrow/central/recovery render evidence. See each trial’s notes for exact evidence and limits.
- quick_validate passes; all skill resource/policy links resolve; `skillset doctor` clean; global Codex list includes
  design-visualization. No scripts or external resources in delivered companions; templates only in intended shell.

Trial gallery `skill-tests/index.html` is linked from main signpost. It includes delivery-view, rotation-view and generic
reference-view. Remaining limits: two bounded fictional trials are not statistical reliability evidence; no live systems,
exhaustive accessibility/print/cross-browser audit or automatic staleness detector. Mobile tables trade scrolling or
page length for legibility; navigation framing may be substantial for short/mobile views. Do not add speculative tooling.

## Continuation and repository cautions

1. Capability ready for operator use. Commit/landing is authorized for this checkpoint; await the next design
   application or operator assessment afterward. Do not silently promote further experimental suggestions.
2. If changes are requested, update canonical skill/policy and run proportionate fidelity/render checks; preserve
   unchanged source authority and accepted visual grammar. Keep design-specific content adaptable.
3. Refresh repository/target state before any publishing/landing. Never revive stale branch or remote references.

Both .agents and `/home/jakub/orca/projects/skillsets` are GitButler-managed; `but status --json` before version control.
Skillsets landed on `origin/main` at `a992fd1ef8c0501d6d9ea44774a63364125f8733` (visualization capability), preceded
by `55cda86d5d28937b1337c5856db9e1dd9299d606` (all earlier dirty skill updates). Remote SHA and clean workspace
verified. This policy/handoff checkpoint is included in the authorized `.agents` landing; inspect its current target
history before further repository work. Both targets were refreshed with `but pull`; no upstream changes were found.
Fresh checks: visualization quick_validate passes, skillset doctor clean, five changed shell scripts pass `bash -n`,
and changed JSON/TOML parse. Earlier workflow updates were preserved rather than redesigned: executing-plans and
subagent-driven-development still refer to the removed finishing-a-development-branch skill. This known reference
gap is an operator-accepted consequence of excluding unwanted upstream skills. Do not patch the obra set after
each update solely to eliminate failed skill reads. No end-to-end behavioral validation of those earlier workflow
changes was performed.
Use skillset-cli for personal collection/discovery management, not ad hoc links or direct lock metadata edits.
The old Caddy Orca worker is unrelated to these native subagent trials; re-list before using it if requested later.

Latest refinement: operator requested main page titles at ~two-thirds size. Shared CSS now uses clamp(24px,3.133vw,42.667px), synchronized delivery/rotation/reference previews; revised C inline scale and mobile override reduced proportionately. Catalog browser cached old CSS initially; cache-busted stylesheet load confirmed 42.667px and no overflow. Title scale is now part of canonical shared asset.

Machine-string refinement: shared review CSS and the Caddy review companion now distinguish inline code with a
neutral background/border, brighter monospace text and .94em sizing. Pattern guidance requires semantic code markup
for literals. Desktop1454 and a 390px-wide browser frame inspected; long paths wrap without page overflow, block
padding remains12px, and review/source HTML bytes are unchanged. Skill CSS/guidance landed on skillsets origin/main at cdd843ba69ae6e14644ce24e377e9f84a0e4d243;
remote SHA and clean workspace verified. Caddy companion CSS committed locally at bda83c17, without landing.
The Taskman mix precommit gate could not run its tests: PostgreSQL at localhost:5432 refused connections.
Browser visual checks and unchanged-source/whitespace checks passed; no application behavior changed.

Current viewport scope: operator rejected routine small-viewport work as unnecessary generation overhead. Policy,
skill and pattern guidance now default to desktop rendering/inspection only. Responsive adaptation and narrow checks
require an explicit operator request; existing CSS remains usable without creating a verification obligation. Skill
quick_validate passes. Skill guidance is landed on skillsets origin/main at
3839181389a9210be283876da1ef89b3a9b2f770; remote SHA and clean workspace verified after refresh. The operator
authorized landing the remaining policy and handoff checkpoint in .agents. Resume from current target history.
The policy also clarifies that substantive companion findings must first be corrected in the authoritative spec,
then synchronized with snapshots/provenance; presentation-only edits remain in the companion.

Existing-skill discovery checkpoint (2026-10-06): source audit and pinned upstream revisions are recorded in
`/home/jakub/.local/share/caddy-design-views/2026-10-03/existing-skills-comparison.md`. Keep our review contract and
presentation shell; diagram-design offers the richest diagram references, effective-html's html-diagram the lightest
specialist. Other candidates add conflicting defaults or serve only as renderers. No candidate was installed, executed
or benchmarked during that source audit. The subsequent operator-approved generation trial is complete below;
no canonical policy/skill changes are authorized by the experiment. This handoff addition remains local and uncommitted.

Two-skill generation trial (2026-10-06): two independent sol/high authors used our framework plus pinned
diagram-design or effective-html's html-diagram. Outputs, same fresh source, provenance and independent assessment:
`/home/jakub/.local/share/caddy-design-views/2026-10-03/skill-comparison-2026-10-06/index.html` and `assessment.md`.
Main signpost links both. Operator prefers diagram-design's styling/readability; html-diagram was too detailed and
diagram-heavy. This supersedes the coordinator's initial html-diagram preference as the operator-fit judgment.
Both preserve statuses and important reviewed boundaries; independent
1440×1080 renders and 62 links/23 decision rows per page pass. One label/routing correction per candidate verified.
No mobile, native behavior or human-review-time testing. Older C uses a different snapshot. Upstream skills were
read from temporary pinned archives, not globally installed or modified. Loopback preview is port 41637, local only.
Second operator-authorized trial is complete: Taskman's named-host/repository-binding draft, at
`/home/jakub/.local/share/caddy-design-views/2026-10-03/repository-bindings-comparison-2026-10-06/index.html`.
Both fresh authors received the Caddy feedback; each selected one ownership diagram and kept exact rules in tables.
Coordinator prefers diagram-design's larger labels/clear routes; html-diagram improved substantially. All ten source
decision IDs/statuses/order and local links pass; independent 1440×1080 renders have no overflow/remote dependencies.
Source remains an unapproved draft: D1 accepted, D2–D10 proposed; unresolved behavior was not finalized.
One connector/label overlap and one proposed-schema wording issue were corrected and independently checked.
Main signpost now lists both designs. `assessment.md` and author notes own detailed evidence and limitations.
Operator slightly prefers html-diagram for the second pair and considers both good, with possible run variance.
Next gate: operator assesses the final repeat before adoption/policy refinement. No canonical skills/policies or source
specs were changed, and no upstream skills were globally installed. Preserve capability baseline/external-action gates.

Third operator-authorized comparison is complete: Taskman's Immediate Cooperative Workspace Updates design at
`/home/jakub/.local/share/caddy-design-views/2026-10-03/live-updates-comparison-2026-10-06/index.html`.
Fresh sol/high authors used the same unchanged approved source and pinned upstream revisions. Diagram-design chose
an explicit database sequence plus conflict state graph; html-diagram chose a compact sequence, conditional rows
and before/after draft comparison. Coordinator slightly prefers html-diagram; operator slightly prefers diagram-design and its maintenance evidence.
Both preserve outer-transaction rollback-after-invalidation limitation, source authority and dated assumptions.
Independent 1440×1080 renders and 30/35 local/source links pass; no overflow/remote assets; snapshot still equals repo.
Detailed assessment, provenance and verification are owned by that experiment directory. Main gallery links all three.
Maintenance audit is `maintenance-comparison-2026-10-06.md` in the gallery root: diagram-design has stronger adoption,
activity and CI/toolkit evidence; effective-html is smaller/maintainer-led with recent maintenance, not abandoned.
Both are young and lack observed tagged releases. Maintenance does not establish rendered-output superiority.
Different-source trials do not isolate run variance; repeating one case would. No source, canonical skills or policies
changed; no upstream installations, commits, landing or publication performed. Local handoff changes remain uncommitted.
Current primary Orca preview page: `0fe78855-676e-4369-a20a-8fcdee07afbd`; loopback port 41637.

Final comparison delivered (2026-10-06): fresh sol/high authors repeated the SAME cooperative-updates snapshot and
pinned upstream revisions, without earlier outputs/rankings. Artifacts and independent assessment:
`/home/jakub/.local/share/caddy-design-views/2026-10-03/live-updates-repeat-2026-10-06/index.html` and `assessment.md`.
Diagram-design selected one participant sequence and tables; html-diagram selected ownership/operation flows and
field comparison tables. Both became longer than their first runs. Coordinator slightly prefers diagram-design for
participant interactions; neither repeat is an unqualified improvement over the first. Operator assessment is pending.
Independent source, 28/26 local/source links, CSS equality and 1440×1080 renders pass; no overflow/remote assets.
One generic no-change label and satisfied-field exception were clarified in html-diagram and independently checked.
Source is unchanged and matches first run/current repo. Main gallery links the final pair and first run.
Brief wording differed slightly, so this qualitative repeat is not a statistical or skill-only causal benchmark.
Operator requested this as the last trial: stop experiments, await final assessment and any explicit adoption decision.
No source or canonical skill/policy changes, installation, commits, landing or publication. Local handoff stays active.

Adoption checkpoint (2026-10-06): operator approved diagram-design as the default specialist. Installed unmodified via
`skillset skills add` into the managed always-on collection (already globally Codex-enabled); restored active set
always-on-m. The collection lock records source cathrynlavery/diagram-design and folder hash
`dc9745b0be384e9a9ff9b9dac08d8d609f7c2154`. The personal design-visualization skill now routes applicable diagrams to it,
keeps our presentation/authority/desktop constraints, skips repeated already-resolved onboarding/type prompts and
preserves suitable diagram types/participant positions on revisions. Proper relationships are drawn explicitly;
ordinary tables remain appropriate for comparison/contracts. Upstream files were not customized.
Skill quick_validate and skillset doctor pass; installed references/resources and global discovery checked.
Default adoption is complete locally. Remaining gate: commit/landing if requested; this checkpoint is uncommitted.
No further experiments are needed. Workstream remains active pending operator confirmation of completion.

Landing checkpoint (2026-10-06): operator authorized stopping the preview server and committing/landing skillsets.
Loopback server on port 41637 stopped; archived HTML artifacts remain on disk. Skillsets origin/main landed at
`0d81a44c57d0efd7e25e16513f839a38594a5e12`; remote SHA equals local target and workspace is clean. quick_validate and skillset doctor pass.
This supersedes the adoption checkpoint’s uncommitted skillsets gate. The .agents handoff edits remain local;
workstream remains active pending explicit completion confirmation.

Optional syntax highlighting checkpoint (2026-10-07): operator approved CDN-based Highlight.js with plain-code offline
fallback. Updated personal design-visualization SKILL.md, shell.html, review.css, reference.html and visual-patterns.md.
Shell/reference use asynchronous Highlight.js 11.12.0 from cdnjs, pinned SRI; local CSS provides token colors. Only
explicit supported language classes on pre/code blocks are highlighted; unknown/unlabeled blocks and inline literals
stay unchanged. No grammar auto-downloads or loading UI. Generated companions without relevant code omit the script.
Independent local Chromium1440 checks: live CDN produces tokens; blocked CDN and JavaScript-disabled views keep
identical code text/padding and no overflow/page errors; unsupported/unlabeled blocks stay plain. Render inspected;
quick_validate and skillset doctor pass. Changed guidance and assets are local/uncommitted; no landing authorized yet.
No existing design companions or upstream diagram-design files changed. Pending operator assessment/commit gate.

Highlighting verification scope clarified (2026-10-07): operator explicitly rejects repeated offline verification during
companion generation. Skill now states fallback was verified during development; ordinary generation inspects rendering
without offline/CDN-blocking/no-JS tests, availability probes or local fallback installs. Recheck only when loader or
fallback behavior changes. Guidance-only clarification; skill validation passes, integration tests were not repeated.
