# Fish Codex Completion Guard Design

## Context

The Fish script emitted by `skillset completions fish` registers completion
conditions for `skillset codex`. Several of those conditions compare the third
completed command token directly, for example:

```fish
test (commandline -xpc)[3] = enable
```

When completion runs for `skillset codex `, only two completed tokens exist.
Fish expands the missing third element to nothing, so `test` receives no left
operand and writes a "Missing argument at index 3" diagnostic to stderr. The
completion candidates still appear, but interactive completion is noisy.

The repository baseline is clean and `python -m unittest discover -s tests`
passes 138 tests with 2 skips. The failure was reproduced with Fish 4.8.1 by
running completion for `skillset codex `.

## Requirements

- Completing `skillset codex ` must produce `enable`, `disable`, and `list`.
- That completion must not write diagnostics to stderr.
- Existing Codex command completion behavior, including skillset-name and
  option candidates, must remain unchanged.
- The regression coverage must exercise Fish's real `complete -C` interface.

## Design

Add a small Fish helper in the generated completion script that:

1. Reads the completed tokens with `commandline -xpc`.
2. Returns false unless a third token exists.
3. Compares that token with its requested Codex subcommand.

Replace each direct third-token comparison in the Codex `enable`, `disable`,
and `list` conditions with the helper. This keeps the token-count safety rule
in one place and preserves the existing completion declarations.

Extend the existing contextual Fish completion test. Its existing probe already
checks Codex subcommand and argument candidates. Add a probe for
`skillset codex ` that asserts both its three candidates and empty stderr.

## Alternatives

- Add a token-count guard to every declaration. This would work, but repeats
  the same safety condition in eight lines.
- Add a separate Fish test. This would duplicate the existing generated-script
  setup and candidate helper without adding coverage the current test cannot
  provide.

The shared helper and extension of the existing contextual test are preferred.

## Verification

Use test-driven development:

1. Extend the contextual Fish completion test and observe its expected failure
   from the current stderr diagnostics.
2. Implement the helper and replace the unsafe conditions.
3. Re-run the focused test and the full `python -m unittest discover -s tests`
   suite.
4. Run Fish syntax validation on the emitted script.
