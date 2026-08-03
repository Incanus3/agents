# Delegation Policy

This policy governs whether and how to delegate work, how to coordinate parallel work, and how to select delegated-agent
models and reasoning effort.

## Delegate with bounded ownership and evidence

Give delegated work a clear output, permitted actions, and acceptance criteria. Assign one owner to each writable
artifact, and isolate concurrent work when changes could collide.

For consequential work, separate implementation from verification and retain artifact-based evidence of the result.

## Delegate only work with a bounded, verifiable contract

Delegate when work is bounded, independently useful, explainable with compact context, and worth more than its
coordination cost. Keep small, serial, or tightly coupled work with the coordinating agent.

For each delegated unit, state the desired output; acceptance criteria and evidence; relevant sources and constraints;
allowed and forbidden actions; writable artifact scope; whether isolation is required; stop, budget, and escalation
conditions; and who integrates and verifies the result. The coordinator remains responsible for synthesis unless that
ownership is explicitly transferred.

## Coordinate parallel work deliberately

Use parallel work only for separable tasks. Prefer read-only discovery fan-out before implementation fan-out, and keep
discovery separate from synthesis when multiple sources or perspectives are useful.

Reconcile conflicting findings explicitly rather than averaging them into false consensus. Stop adding workers when
coordination cost approaches the expected gain.

## Select delegated-agent models and reasoning effort

Use these defaults when choosing a model and reasoning effort for delegated work:

- Strongly prefer `gpt-5.6-luna` with `max` reasoning for most implementation
  work. For unusually risky or ambiguous implementation work, consider
  `gpt-5.6-terra` with `xhigh` reasoning or `gpt-5.6-sol` with `medium`
  reasoning instead.
- Prefer `gpt-5.6-sol` with `medium` reasoning or `gpt-5.6-terra` with `xhigh`
  reasoning for most verification work. When practical, use a different
  GPT-5.6 model variant for verification than was used for implementation.
- Prefer `gpt-5.6-sol` with `medium` reasoning for most software design and
  architecture work. This does not apply to visual or UI design.
- Use `gpt-5.6-sol` with `high` reasoning sparingly, only for strictly bounded
  software design work or mission-critical verification. Sol at `high` is very
  expensive.

Enforce these per-model reasoning limits:

- For `gpt-5.6-luna`, strongly prefer `max`. Use `xhigh` only when latency has
  a concrete operational consequence and the task is low-criticality, bounded,
  reversible, and independently verifiable. A person merely waiting for the
  result does not qualify. Do not downgrade because a task appears simple.
  When uncertain, use `max`. Use `high` only with explicit operator
  authorization; never autonomously use `low`, `medium`, or `high`.
- For `gpt-5.6-terra`, use only `high` or `xhigh`. Never use `low`, `medium`, or
  `max`.
- For `gpt-5.6-sol`, normally use `medium`; use `high` only in the narrow cases
  above. Never use `low`, `xhigh`, or `max`.

An explicit operator instruction may authorize a model-and-effort combination
prohibited above. Treat the exception as specific to that instruction; never
infer or generalize it.
