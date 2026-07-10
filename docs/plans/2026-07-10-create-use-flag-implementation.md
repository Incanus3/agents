# Create-and-Activate Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development`
> (recommended) or `executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `skillset create --use` so an empty or cloned skillset can be created and
activated in one command, with options accepted before or after the set name.

**Architecture:** Keep `create` and `use` as independent filesystem operations. Add a
boolean create-parser option and compose the existing operations in CLI dispatch under
the command's existing HOME and managed-layout locks.

**Source of truth:** `docs/specs/2026-07-10-create-use-flag-design.md`

**Tracking:** `agents-023`

**Tech Stack:** Linux, Python 3 standard library, `argparse`, `unittest`, filesystem
fault injection through the existing `sitecustomize.py` test helper, and Jujutsu.

## Global Constraints

- Support `skillset create NAME --use`, `skillset create --use NAME`, and both
  equivalent clone forms using `--from SOURCE`.
- Without `--use`, creation must remain inactive and backward compatible.
- Creation commits before activation begins; activation failure must never delete the
  new set.
- Preserve the existing `create(root, name, source)` and `use(root, name)` signatures
  and their separate atomic boundaries.
- Keep the stable root `skills` and `.skill-lock.json` aliases unchanged.
- Use only the Python 3 standard library; add no dependency or package change.
- Tests must use isolated temporary HOME directories and must never mutate the real
  `~/.agents` layout.
- Do not modify or remove the unrelated uncommitted
  `skillsets/minimal/.skill-lock.json` present when this plan was written.
- Do not commit without explicit user permission.

---

### Task 1: Create and activate through one command

**Files:**
- Modify: `tests/test_skillset.py:1905-2110`
- Modify: `lib/skillset/cli.py:27-91`
- Modify: `README.md:29-53`

**Interfaces:**
- Consumes: existing `create(root: Path, name: str, source: str | None) -> None` and
  `use(root: Path, name: str) -> None` operations.
- Produces: `skillset create [--use] NAME [--from SOURCE]`, where parsed
  `arguments.activate: bool` controls whether dispatch calls `use` after `create`.
- Preserves: exit status 0 on complete success, status 1 for operational failures,
  status 2 for argparse usage errors, and existing atomic/recovery behavior.

- [ ] **Step 1: Add RED tests for successful activation and flexible option order**

Add a black-box test beside the existing create tests. Use four independent HOME
directories so every required spelling is exercised from the same initial state:

```python
def test_create_use_activates_with_options_before_and_after_name(self):
    cases = (
        ("empty-after", ("create", "empty-after", "--use"), False),
        ("empty-before", ("create", "--use", "empty-before"), False),
        ("clone-after", ("create", "clone-after", "--from", "default", "--use"), True),
        ("clone-before", ("create", "--use", "--from", "default", "clone-before"), True),
    )
    for index, (name, arguments, cloned) in enumerate(cases):
        home = self.new_home(f"create-use-{index}")
        root = self.make_managed_layout(home)
        source = root / "skillsets" / "default"
        (source / "skills" / "source-marker").write_bytes(b"source payload")
        lock_bytes = b'{"version":3,"skills":{},"dismissed":{}}\n'
        (source / ".skill-lock.json").write_bytes(lock_bytes)
        result = self.run_cli(*arguments, home=home)
        with self.subTest(arguments=arguments):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assert_aliases(root, name)
            target = root / "skillsets" / name
            if cloned:
                self.assertEqual(
                    (target / "skills" / "source-marker").read_bytes(),
                    b"source payload",
                )
                self.assertEqual((target / ".skill-lock.json").read_bytes(), lock_bytes)
            else:
                self.assert_empty_set(root, name)
```

Retain `test_create_empty_set_without_changing_active_set` and
`test_create_from_clones_complete_state_exactly`; they lock backward compatibility when
`--use` is absent.

- [ ] **Step 2: Add RED tests at both activation failure boundaries**

First add a creation-failure test proving activation is never attempted:

```python
def test_create_use_creation_failure_does_not_change_active_set(self):
    self.initialize()
    occupied = self.make_set(self.root, "occupied")
    marker = occupied / "skills" / "keep"
    marker.write_bytes(b"untouched")
    result = self.run_cli("create", "occupied", "--use")
    self.assert_refused(result)
    self.assertEqual(marker.read_bytes(), b"untouched")
    self.assert_aliases(self.root, "default")
```

Add one pre-replacement fault test. It must prove that creation remains committed, the
old set remains active, the stable aliases are unchanged, and canonical use staging is
cleaned after an ordinary exception:

```python
def test_create_use_activation_failure_keeps_new_set_and_previous_active(self):
    self.initialize()
    fault = self.fault_environment(f"""
        import os
        active = {str(self.root / 'active')!r}
        original_replace = os.replace
        def fail_active(source, destination, *args, **kwargs):
            if os.path.abspath(os.fspath(destination)) == active:
                raise OSError("injected activation failure")
            return original_replace(source, destination, *args, **kwargs)
        os.replace = fail_active
    """)
    stable = {name: os.readlink(self.root / name)
              for name in ("active", "skills", ".skill-lock.json")}
    result = self.run_cli("create", "experiment", "--use", extra_environment=fault)
    self.assert_refused(result)
    self.assert_empty_set(self.root, "experiment")
    self.assertEqual({name: os.readlink(self.root / name) for name in stable}, stable)
    self.assertFalse(os.path.lexists(self.root / ".skillset-use.staging"))
```

Add a post-replacement fault test by wrapping the real `os.replace` before raising. It
must prove that the committed active target remains the new set even though the command
reports the existing activation error:

```python
def test_create_use_post_replace_failure_preserves_committed_activation(self):
    self.initialize()
    fault = self.fault_environment(f"""
        import os
        active = {str(self.root / 'active')!r}
        original_replace = os.replace
        def fail_after_active(source, destination, *args, **kwargs):
            result = original_replace(source, destination, *args, **kwargs)
            if os.path.abspath(os.fspath(destination)) == active:
                raise OSError("injected post-replacement failure")
            return result
        os.replace = fail_after_active
    """)
    result = self.run_cli("create", "experiment", "--use", extra_environment=fault)
    self.assert_refused(result)
    self.assert_empty_set(self.root, "experiment")
    self.assert_aliases(self.root, "experiment")
    self.assertFalse(os.path.lexists(self.root / ".skillset-use.staging"))
```

Extend `test_argparse_usage_errors_exit_two` with
`("create", "new", "--unknown")`. Add a focused help assertion:

```python
def test_create_help_documents_use_option(self):
    result = self.run_cli("create", "--help")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("--use", result.stdout)
```

- [ ] **Step 3: Run focused tests and verify RED**

Run each new test directly:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_create_use_activates_with_options_before_and_after_name \
  tests.test_skillset.SkillsetTests.test_create_use_creation_failure_does_not_change_active_set \
  tests.test_skillset.SkillsetTests.test_create_use_activation_failure_keeps_new_set_and_previous_active \
  tests.test_skillset.SkillsetTests.test_create_use_post_replace_failure_preserves_committed_activation \
  tests.test_skillset.SkillsetTests.test_create_help_documents_use_option
```

Expected: failures because the create parser does not recognize `--use`; successful
activation assertions must not pass accidentally. Confirm the pre-existing create tests
still pass independently.

- [ ] **Step 4: Implement the minimal parser and dispatch composition**

In `parser()`, add the option to `create_parser` after `--from`:

```python
create_parser.add_argument(
    "--use",
    dest="activate",
    action="store_true",
    help="activate the created skillset",
)
```

In the `arguments.command == "create"` branch, compose existing operations:

```python
create(root, arguments.name, arguments.source)
if arguments.activate:
    use(root, arguments.name)
```

Do not change `lib/skillset/operations.py`, add combined rollback, or catch an error
between these calls. Normal unwinding must preserve each operation's existing outcome.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the exact command from Step 3, then run the existing create/use neighborhood:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_create_empty_set_without_changing_active_set \
  tests.test_skillset.SkillsetTests.test_create_from_clones_complete_state_exactly \
  tests.test_skillset.SkillsetTests.test_failed_atomic_use_keeps_previous_active_set_and_aliases
```

Expected: all selected tests pass with exit status 0. The post-replacement test is
expected to observe command status 1 while its filesystem assertions pass.

- [ ] **Step 6: Document immediate activation**

In README's “Create skillsets” section, keep the inactive examples and add:

```text
Create and activate an empty set in one command:

    skillset create --use experiment

Clone and activate in one command:

    skillset create --use --from default experiment
```

State that options may appear before or after `NAME`. Explain concisely that if
creation succeeds but activation fails before replacement, the new set remains and the
previous set stays active; the user can inspect it and retry `skillset use NAME`.

- [ ] **Step 7: Run complete verification and inspect the diff**

Run:

```sh
python3 -m unittest discover -s tests -v
jj diff --summary
jj diff -- README.md lib/skillset/cli.py tests/test_skillset.py \
  docs/specs/2026-07-10-create-use-flag-design.md \
  docs/plans/2026-07-10-create-use-flag-implementation.md
```

Expected: the test command exits 0 with no failures or errors. The diff contains only
the approved feature, its tests/docs, the specification, and this plan; it must not
alter `skillsets/minimal/.skill-lock.json`. Confirm no internal planning terminology
was added to production code, test names, CLI help, or README.

- [ ] **Step 8: Report the checkpoint**

Summarize changed behavior, exact verification evidence, and any caveat. Encourage the
user to commit the completed slice, but do not run `jj commit` unless they explicitly
authorize it.
