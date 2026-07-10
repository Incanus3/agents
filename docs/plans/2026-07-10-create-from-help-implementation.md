# Create `--from` Help Implementation Plan

> **For agentic workers:** Use `subagent-driven-development` or `executing-plans` to
> implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explain `--from SOURCE` in `skillset create -h` with the exact text
`clone from an existing skillset`.

**Architecture:** Add help metadata to the existing `argparse` argument and verify the
rendered subprocess output. Do not change parsing or lifecycle operations.

**Source of truth:** `docs/specs/2026-07-10-create-from-help-design.md`
**Tracking:** `agents-xnq`
**Tech stack:** Python 3 standard library and `unittest` black-box subprocess tests.

## Global constraints

- The exact description is `clone from an existing skillset`.
- Preserve all command behavior, parsing, option order, exit statuses, and filesystem
  semantics.
- Use isolated test HOME directories; never mutate real managed state.
- Modify only `lib/skillset/cli.py` and `tests/test_skillset.py` for implementation.
- Do not touch `skillsets/minimal/.skill-lock.json` or unrelated working-copy changes.
- Do not commit without explicit user permission.

---

### Task 1: Describe the clone source in create help

**Files:**
- Modify: `tests/test_skillset.py:2018-2022`
- Modify: `lib/skillset/cli.py:32-40`

**Interfaces:**
- Consumes: existing `SkillsetArgumentParser` create subparser.
- Produces: create help containing
  `--from SOURCE  clone from an existing skillset`.
- Preserves: `arguments.source` parsing and all operation signatures.

- [ ] **Step 1: Add the failing black-box assertion**

Extend the existing test without duplicating subprocess setup:

```python
def test_create_help_documents_create_options(self):
    result = self.run_cli("create", "--help")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("--from SOURCE", result.stdout)
    self.assertIn("clone from an existing skillset", result.stdout)
    self.assertIn("--use", result.stdout)
```

Rename the existing test from `test_create_help_documents_use_option` to
`test_create_help_documents_create_options` because it now covers both options.

- [ ] **Step 2: Run focused RED verification**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_create_help_documents_create_options
```

Expected: one failure because `clone from an existing skillset` is absent. The help
command itself must still exit 0 and include `--from SOURCE` and `--use`.

- [ ] **Step 3: Add the exact argument help text**

Replace the one-line `--from` declaration with:

```python
create_parser.add_argument(
    "--from",
    dest="source",
    metavar="SOURCE",
    help="clone from an existing skillset",
)
```

Do not change any other parser declaration or dispatch code.

- [ ] **Step 4: Run focused GREEN verification**

Run the exact command from Step 2. Expected: one test passes, output ends with `OK`,
and exit status is 0.

- [ ] **Step 5: Run complete verification**

Run:

```sh
python3 -m unittest discover -s tests -v
```

Expected: all tests pass with no warnings or errors and exit status 0.

- [ ] **Step 6: Review the scoped diff**

Run:

```sh
jj diff --git -- lib/skillset/cli.py tests/test_skillset.py
```

Confirm the bead adds only the exact help metadata and focused assertion on top of the
already verified `create --use` changes. Request a read-only review before completion.

- [ ] **Step 7: Close the checkpoint**

Close and flush `agents-xnq`, report RED/GREEN and full-suite evidence, encourage the
user to commit the accumulated changes, and stop. Do not create a commit without
explicit permission.
