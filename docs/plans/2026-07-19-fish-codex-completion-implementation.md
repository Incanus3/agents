# Fish Codex Completion Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use the repository's approved execution workflow to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Fish from emitting diagnostics while completing `skillset codex` commands.

**Architecture:** The generated Fish completion script will gain a focused predicate for matching the nested Codex command only when that completed token exists. The existing Fish integration test will exercise `complete -C` for the partial Codex command and require clean stderr for every candidate probe.

**Tech Stack:** Python 3 standard-library `unittest`; Fish shell completion declarations.

## Global Constraints

- Keep the generated completion interface and candidate sets unchanged except for removing Fish diagnostics.
- Exercise Fish through its real `complete -C` interface; do not mock Fish parsing.
- Do not add dependencies.
- Use `but` for version-control operations in this workspace.

---

### Task 1: Guard nested Codex completion conditions

**Files:**

- Modify: `tests/test_skillset.py:539-568`
- Modify: `lib/skillset/completions.py:266-346`
- Modify: `docs/specs/2026-07-19-fish-codex-completion-design.md` (only if the implemented names differ from this plan)

**Interfaces:**

- Consumes: Fish `commandline -xpc`, whose elements are completed command tokens.
- Produces: `__skillset_using_codex_command <enable|disable|list>`, a Fish predicate that returns true only when the third completed token matches its argument.

- [x] **Step 1: Extend the existing real-Fish completion probe to require clean stderr and cover the partial Codex command.**

  In `test_fish_completion_is_contextual_and_uses_managed_names`, add an empty-stderr assertion inside the existing `candidates` helper immediately after the return-code assertion:

  ```python
  self.assertEqual(result.returncode, 0, result.stderr)
  self.assertEqual(result.stderr, "")
  return [line.split("\t", 1)[0] for line in result.stdout.splitlines()]
  ```

  Add the reported partial-command assertion immediately before the existing `skillset codex e` assertion:

  ```python
  self.assertEqual(
      candidates("skillset codex "),
      ["disable", "enable", "list"],
  )
  self.assertEqual(candidates("skillset codex e"), ["enable"])
  ```

- [x] **Step 2: Run the focused test and verify it fails because Fish writes the missing-argument diagnostics.**

  Run:

  ```bash
  python -m unittest tests.test_skillset.SkillsetTests.test_fish_completion_is_contextual_and_uses_managed_names
  ```

  Expected: failure at `self.assertEqual(result.stderr, "")`, with Fish's `test: Missing argument at index 3` diagnostic in the captured stderr.

- [x] **Step 3: Add the safe nested-command predicate and use it in every Codex completion condition.**

  After `__skillset_using_command` in the `FISH` script constant, add:

  ```fish
  function __skillset_using_codex_command
      set -l tokens (commandline -xpc)
      test (count $tokens) -ge 3; and test $tokens[3] = $argv[1]
  end
  ```

  Replace the nine direct conditions that use `test (commandline -xpc)[3] = ...` with the matching helper invocation. The resulting declarations must be:

  ```fish
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command enable; and __skillset_at_position 1' -a '(__skillset_names)'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command disable; and __skillset_at_position 1' -a '(__skillset_names)'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command enable' -s g -l global -d 'Manage global Codex skills'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command enable' -s l -l local -d 'Manage local Codex skills'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command disable' -s g -l global -d 'Manage global Codex skills'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command disable' -s l -l local -d 'Manage local Codex skills'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command list' -s v -l verbose -d 'Show skill inventory'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command list' -s g -l global -d 'List global Codex skills'
  complete -c skillset -n '__skillset_using_command codex; and __skillset_using_codex_command list' -s l -l local -d 'List local Codex skills'
  ```

- [x] **Step 4: Run the focused regression test and verify it passes.**

  Run:

  ```bash
  python -m unittest tests.test_skillset.SkillsetTests.test_fish_completion_is_contextual_and_uses_managed_names
  ```

  Expected: `OK`; the partial command returns `disable`, `enable`, and `list`, and every completion probe has empty stderr.

- [x] **Step 5: Validate the generated Fish script and run the full suite.**

  Run:

  ```bash
  bin/skillset completions fish | fish -n
  python -m unittest discover -s tests
  ```

  Expected: Fish exits 0 with no syntax diagnostics; the Python suite exits 0 with all tests passing (two optional-shell skips are acceptable if Zsh is unavailable).

- [x] **Step 6: Inspect the final diff, check for leaked planning terminology, and commit the implementation.**

  Run:

  ```bash
  but diff
  rg -n 'TBD|TODO|milestone|ticket|phase|superpowers' lib/skillset/completions.py tests/test_skillset.py
  but status --format json
  but commit dev --message 'fix: guard Fish Codex completion conditions' --format json
  ```

  Expected: only the Fish script and its regression test change; the terminology search has no unintended product-surface matches; the commit succeeds on `dev`.
