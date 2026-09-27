# Delegation Policy

This policy governs whether and how to delegate work, how to coordinate parallel work, and how to select delegated-agent
models and reasoning effort.

## Use model families according to the work

Never use an `astra` model as a subagent. Never use a `sol` model with reasoning effort above `high`
as a subagent. For primary-agent planning and design, prefer `sol` at `high`, and use `xhigh` when
the work warrants deeper reasoning. Use `astra` for demanding primary-agent work; reasoning effort
above `low` is very expensive and needs a clear expected benefit.

Use an available `sol` model at `medium` or `high` for substantive delegated work. Choose `high`
for the most complex or mission-critical tasks, especially independent verification. Use an
available `luna` model at `max` for routine implementation, exploration, and verification. Avoid
`sol` at `low` and `luna` below `max`; these configurations are not preferred workhorse choices.
For eligible subagents, follow an explicit operator model choice when the selected model is
available and permitted by the execution environment.

## Default to delegation for implementation and code verification

Delegate implementation and code-verification work unless it is genuinely trivial. Treat work as trivial only when it
is small, local, low-risk, reversible, requires no meaningful design judgment, and would cost more to explain and
coordinate than to perform directly. Do not classify work as trivial merely because an experienced agent can complete
it quickly.

Keep implementation and verification with the main agent only for these simplest tasks. Once a reviewed implementation
plan provides clear scope, constraints, acceptance criteria, and file ownership, delegate its implementation and
independent verification to separate agents selected according to the model and reasoning-effort rules below. The main
agent remains responsible for integration, synthesis, unresolved decisions, and the final report.

## Keep design ownership with the main agent

Keep software design, architecture, trade-off resolution, specification writing, and implementation-plan synthesis
with the main agent by default. Delegate bounded, preferably read-only exploration when independent repository
discovery, external research, or comparison of alternatives would improve the design.

Exploration workers return evidence and options; they do not silently become owners of the design. The main agent
reconciles their findings, resolves conflicts, and confirms that the resulting plan has been reviewed and is ready
before delegating implementation.

## Delegate only work with a bounded, verifiable contract

Delegate work in units that are bounded, independently useful, explainable with compact context, and worth their
coordination cost. Keep tightly coupled tasks together when separating them would create ambiguous ownership or
convoluted dependencies.

For each delegated unit, state the desired output; acceptance criteria and evidence; relevant sources and constraints;
allowed and forbidden actions; writable artifact scope; whether isolation is required; stop, budget, and escalation
conditions; and who integrates and verifies the result. The coordinator remains responsible for synthesis unless that
ownership is explicitly transferred.

## Separate implementation from verification

Never assign implementation and independent verification of the same change to the same subagent or agent session. A
verifier must be a distinct agent that did not implement or materially assist with the change being verified.

An implementation agent may run tests and self-checks while developing, but those checks do not count as independent
verification. For consequential work, retain artifact-based evidence from both the implementer and the independent
verifier.

## Coordinate parallel work deliberately

Use parallel work only for separable tasks. Prefer read-only discovery fan-out before implementation fan-out, and keep
discovery separate from synthesis when multiple sources or perspectives are useful.

Reconcile conflicting findings explicitly rather than averaging them into false consensus. Stop adding workers when
coordination cost approaches the expected gain.
