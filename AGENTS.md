# Global Agent Conventions

These rules capture general practices that should carry across projects and sessions.

## Use tool-neutral documentation paths

Store design artifacts in stable, purpose-based directories:

- Specifications: `docs/specs/`
- Implementation plans: `docs/plans/`
- Session handoffs: `docs/handoffs/`

Do not put workflow, skill collection, or tool names such as `superpowers` in documentation directory names unless the
documents are specifically about that tool. Tool-neutral paths remain accurate when workflows or agents change.

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

## Mirror upstream vocabulary in wrapper CLIs

When a CLI delegates to another CLI, reuse the upstream command verbs and option names wherever the semantics match.
Avoid unnecessary synonyms such as `delete` for an upstream `remove` command or `switch` for an upstream `use` command.
Matching vocabulary reduces translation overhead and makes upstream documentation easier to apply.

## Inventory all persistent state before designing indirection

Before introducing profiles, switching, aliases, or symlink-based indirection, identify all state used by the underlying
tool. Inspect visible data directories as well as lockfiles, metadata, caches, links, and state-directory environment
variables.

Keep related data and metadata together. Switching visible files without their associated metadata can leave management
commands operating on a different logical state than the files currently in use.

## Treat rewriting pushed Jujutsu history as exceptional

Only bypass immutable-commit protection when the user explicitly requests rewriting pushed history. Do not weaken the
repository's immutable-head configuration for a one-off rewrite.

When a rewrite is authorized:

1. Use the command-scoped `--ignore-immutable` override.
2. Push through Jujutsu with the intended bookmark explicitly selected.
3. Verify that the local and remote commit IDs match after the push.