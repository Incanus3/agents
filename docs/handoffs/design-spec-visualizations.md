# Design specification visualizations

- Status: active
- Updated: 2026-10-03
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
gap needs separate follow-up; no end-to-end behavioral validation of those earlier workflow changes was performed.
Use skillset-cli for personal collection/discovery management, not ad hoc links or direct lock metadata edits.
The old Caddy Orca worker is unrelated to these native subagent trials; re-list before using it if requested later.

Latest refinement: operator requested main page titles at ~two-thirds size. Shared CSS now uses clamp(24px,3.133vw,42.667px), synchronized delivery/rotation/reference previews; revised C inline scale and mobile override reduced proportionately. Catalog browser cached old CSS initially; cache-busted stylesheet load confirmed 42.667px and no overflow. Title scale is now part of canonical shared asset.
