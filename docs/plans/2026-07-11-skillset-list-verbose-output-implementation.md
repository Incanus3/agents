# Friendlier `skillset list -v` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace tab-separated verbose skillset listing with a safe, aligned, complete, TTY-aware two-column table.

**Architecture:** Keep inspection and plain `list` semantics unchanged. Build structured verbose rows in
`lib/skillset/metadata.py`, derive plain text and display widths before rendering, and style independent cell segments
only for eligible TTY output. Keep the renderer list-specific while preserving a clean future extraction seam.

**Source of truth:** `docs/specs/2026-07-11-skillset-list-verbose-output-design.md`

**Tracking:** `agents-7eo`

**Tech stack:** Python 3 standard library, ANSI SGR sequences, Linux pseudo-terminals, and black-box `unittest` tests.

## Global constraints

- Preserve argument parsing, full-layout validation, locking, error text, exit statuses, stderr, and read-only behavior.
- Keep non-verbose `skillset list` byte-for-byte unchanged.
- Emit color only when stdout is a TTY, `NO_COLOR` is absent, and `TERM` is not `dumb`.
- Sanitize every user-controlled display value with `printable_text` before width calculation or ANSI styling.
- Keep every skillset on one physical data line; never wrap, truncate, or add an ellipsis.
- Use no third-party dependency and add no color-control option.
- Do not refactor `show` or create a terminal-rendering module in this bead.
- Do not commit, change bead status, or close the bead without explicit user permission.
- If any Jujutsu command reports that the working copy is stale, stop immediately and ask the user to resolve it.

## File map

- `lib/skillset/metadata.py`: collect structured verbose rows and render plain or styled output.
- `tests/test_skillset.py`: lock plain, Unicode, sanitization, TTY, opt-out, width, and read-only contracts.
- `README.md`: document the verbose table, invalid entries, empty cells, and automatic color.
- `docs/specs/2026-07-10-named-skillsets-cli-design.md`: replace the superseded verbose-list contract.
- `lib/skillset/cli.py`: no change expected; it already dispatches `list_sets(root, arguments.verbose)`.

---

### Task 1: Structured inventory and deterministic plain table

**Files:**
- Modify: `tests/test_skillset.py:1030-1091`
- Modify: `lib/skillset/metadata.py:220-234`, reusing helpers at `241-281`

**Interfaces:**
- Consumes: `inspect_skills(skills) -> list[tuple]`, `set_path(root, name) -> Path`, `printable_text(value) -> str`,
  `display_width(value) -> int`, and `validate_layout(root) -> str`.
- Produces: `skill_entry_text(entry) -> str`, `verbose_skill_entries(skills) -> list[tuple]`,
  `verbose_list_rows(root, names, active_name) -> list[tuple]`, `render_verbose_list(rows, output) -> None`, and
  `list_sets(root, verbose, output=None) -> None`.
- Structured entry: `(display_name, annotation_or_none, reason_or_none)`.
- Structured row: `(is_active, sanitized_set_name, entries)`.

Before editing, obtain explicit permission to change bead status, then run `br update agents-7eo --status=in_progress`.

- [ ] **Step 1: Update the existing verbose-list test to the exact RED contract**

Rename `test_list_supports_both_verbose_flags_with_sorted_valid_declared_names` to
`test_verbose_list_prints_aligned_complete_inventory_for_both_flags`. Keep its setup, then replace the expected output:

```python
skills_cell = "alpha, malformed [invalid: missing description], zeta"
expected = (
    "  SKILLSET | SKILLS\n"
    "  ---------|" + "-" * (len(skills_cell) + 1) + "\n"
    f"* default  | {skills_cell}\n"
    "  empty    | (no skills)\n"
)
for flag in ("-v", "--verbose"):
    with self.subTest(flag=flag):
        result = self.run_cli("list", flag)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("\x1b", result.stdout)
```

- [ ] **Step 2: Add RED coverage for invalid-only inventory and Unicode display width**

Add these tests beside the existing list tests:

```python
def test_verbose_list_does_not_call_an_invalid_only_set_empty(self):
    self.initialize()
    broken = self.make_set(self.root, "broken-only")
    self.write_skill(broken / "skills", "malformed", "name: hidden")

    result = self.run_cli("list", "-v")

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn(
        "  broken-only | malformed [invalid: missing description]\n",
        result.stdout,
    )
    self.assertNotIn("  broken-only | (no skills)\n", result.stdout)

def test_verbose_list_measures_wide_and_combining_skill_names_by_display_cell(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    combining = "e\u0301" * 6
    self.write_skill(skills, "combining", f"name: {combining}\ndescription: valid")
    self.write_skill(skills, "wide", "name: 界界界\ndescription: valid")

    result = self.run_cli("list", "-v")

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout.splitlines()[1], "  ---------|" + "-" * 15)
    self.assertEqual(result.stdout.splitlines()[2], f"* default  | {combining}, 界界界")
```

The skills cell in the Unicode test occupies 14 terminal cells: six for the combining sequence, two for `, `, and six
for the wide characters. The separator therefore has 15 right-side dashes.

- [ ] **Step 3: Update the control-character test to expect the table without weakening its safety assertions**

In `test_verbose_list_visibly_escapes_declared_name_terminal_controls`, replace the old exact output and tab assertion:

```python
displayed = r"jalapeño\x1b\x7f\u202eoutil"
self.assertEqual(
    result.stdout,
    "  SKILLSET | SKILLS\n"
    "  ---------|" + "-" * (len(displayed) + 1) + "\n"
    f"* default  | {displayed}\n",
)
self.assertIn("jalapeño", result.stdout)
self.assertNotIn("\t", result.stdout)
```

Retain the existing raw-control loop, stderr assertion, and filesystem snapshot assertion.

Add equivalent coverage for an invalid directory name, whose text follows a separate rendering branch:

```python
def test_verbose_list_visibly_escapes_invalid_directory_terminal_controls(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    directory = "broken\x1b\x7f\u202ename"
    (skills / directory).mkdir()

    result = self.run_cli("list", "--verbose")

    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stderr, "")
    for raw in ("\x1b", "\x7f", "\u202e"):
        self.assertNotIn(raw, result.stdout)
    self.assertIn(
        r"broken\x1b\x7f\u202ename [invalid: missing SKILL.md]",
        result.stdout,
    )
```

- [ ] **Step 4: Run focused tests and verify the expected RED failure**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_verbose_list_prints_aligned_complete_inventory_for_both_flags \
  tests.test_skillset.SkillsetTests.test_verbose_list_does_not_call_an_invalid_only_set_empty \
  tests.test_skillset.SkillsetTests.test_verbose_list_measures_wide_and_combining_skill_names_by_display_cell \
  tests.test_skillset.SkillsetTests.test_verbose_list_visibly_escapes_declared_name_terminal_controls \
  tests.test_skillset.SkillsetTests.test_verbose_list_visibly_escapes_invalid_directory_terminal_controls
```

Expected: the command exits nonzero because current output is tab-separated, malformed entries are omitted, and no
headers or separator exist. Safety setup and filesystem assertions must not fail.

- [ ] **Step 5: Implement structured entries, rows, and plain rendering**

Replace the current `list_sets` block with the following helpers and operation. They may remain above the ANSI constants;
Python resolves those globals when the functions are called after module initialization.

```python
def skill_entry_text(entry):
    display_name, annotation, _reason = entry
    return display_name if annotation is None else f"{display_name} {annotation}"


def verbose_skill_entries(skills):
    entries = []
    for directory, declared, _description, reason in inspect_skills(skills):
        if reason is None:
            display_name = printable_text(declared)
            annotation = None
        else:
            display_name = printable_text(directory)
            annotation = f"[invalid: {reason}]"
        entries.append((display_name, annotation, reason))
    return sorted(entries, key=lambda entry: (entry[0], skill_entry_text(entry)))


def verbose_list_rows(root, names, active_name):
    return [
        (
            name == active_name,
            printable_text(name),
            verbose_skill_entries(set_path(root, name) / "skills"),
        )
        for name in names
    ]


def render_verbose_list(rows, output):
    skill_cells = [
        ", ".join(skill_entry_text(entry) for entry in entries)
        if entries
        else "(no skills)"
        for _active, _name, entries in rows
    ]
    left_width = max(display_width("SKILLSET"), *(display_width(row[1]) for row in rows))
    right_width = max(display_width("SKILLS"), *(display_width(cell) for cell in skill_cells))
    print(f"  {pad_display('SKILLSET', left_width)} | SKILLS", file=output)
    print("  " + "-" * (left_width + 1) + "|" + "-" * (right_width + 1), file=output)
    for (active, name, _entries), skill_cell in zip(rows, skill_cells):
        marker = "* " if active else "  "
        print(f"{marker}{pad_display(name, left_width)} | {skill_cell}", file=output)


def list_sets(root, verbose, output=None):
    output = sys.stdout if output is None else output
    active_name = validate_layout(root)
    names = sorted(entry.name for entry in (root / "skillsets").iterdir())
    if not verbose:
        for name in names:
            marker = "* " if name == active_name else ""
            print(f"{marker}{name}", file=output)
        return
    render_verbose_list(verbose_list_rows(root, names, active_name), output)
```

Do not move metadata parsing or filesystem traversal into the renderer. Do not pad the final skills cell.

- [ ] **Step 6: Run focused GREEN tests plus plain-list and read-only regressions**

Run the Step 4 command, then:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_list_sorts_set_names_and_marks_only_the_active_set \
  tests.test_skillset.SkillsetTests.test_successful_inspection_commands_are_strictly_read_only
```

Expected: both commands exit 0; the first runs five tests and the second runs two tests. Plain listing remains exact and
inspection leaves the filesystem snapshot unchanged.

- [ ] **Step 7: Review the diff and request permission before committing this checkpoint**

Run `jj diff -- tests/test_skillset.py lib/skillset/metadata.py`. Confirm only Task 1 changes are present. If the user
authorizes a commit, run:

```sh
jj commit -m "Render complete verbose skillset inventory"
```

---

### Task 2: Safe segmented TTY styling and terminal-width separator

**Files:**
- Modify: `tests/test_skillset.py` beside the verbose-list tests
- Modify: `lib/skillset/metadata.py` in `render_verbose_list` and one new rendering helper

**Interfaces:**
- Consumes: Task 1 structured entries/rows plus existing `color_enabled`, `terminal_width`, and `styled` helpers.
- Produces: `render_skill_entries(entries, colored) -> str` and styled `render_verbose_list(rows, output) -> None`.
- Preserves: identical plain bytes when color is disabled and one physical line per skillset.

- [ ] **Step 1: Add RED tests for exact eligible-TTY segment styles**

```python
def test_verbose_list_colorizes_independent_segments_only_for_eligible_tty(self):
    self.initialize()
    self.make_set(self.root, "empty")
    skills = self.root / "skillsets/default/skills"
    self.write_skill(skills, "valid", "name: alpha\ndescription: valid")
    self.write_skill(skills, "warning", "name: warning")
    (skills / "error").mkdir()

    colored = self.run_cli_tty("list", "-v")

    self.assertEqual(colored.returncode, 0, colored.stderr)
    self.assertIn("\x1b[1mSKILLSET\x1b[0m", colored.stdout)
    self.assertIn("\x1b[2m|\x1b[0m", colored.stdout)
    self.assertRegex(colored.stdout, r"\x1b\[2m  -+\|-+\x1b\[0m")
    self.assertIn("\x1b[1m\x1b[36m*\x1b[0m ", colored.stdout)
    self.assertIn("\x1b[1m\x1b[36mdefault\x1b[0m", colored.stdout)
    self.assertIn("\x1b[36malpha\x1b[0m, error ", colored.stdout)
    self.assertIn("\x1b[31m[invalid: missing SKILL.md]\x1b[0m", colored.stdout)
    self.assertIn("\x1b[33m[invalid: missing description]\x1b[0m", colored.stdout)
    self.assertIn("\x1b[2m(no skills)\x1b[0m", colored.stdout)

    plain = self.run_cli("list", "-v")
    self.assertNotIn("\x1b", plain.stdout)
```

- [ ] **Step 2: Add RED tests for opt-outs, narrow separators, and untruncated rows**

```python
def test_verbose_list_tty_color_honors_environment_opt_outs(self):
    self.initialize()
    self.write_skill(
        self.root / "skillsets/default/skills",
        "valid",
        "name: alpha\ndescription: valid",
    )
    plain = self.run_cli("list", "-v").stdout
    for extra_environment in ({"NO_COLOR": "1"}, {"TERM": "dumb"}):
        with self.subTest(environment=extra_environment):
            result = self.run_cli_tty(
                "list", "-v", extra_environment=extra_environment
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, plain)
            self.assertNotIn("\x1b", result.stdout)

def test_verbose_list_caps_only_tty_separator_and_keeps_one_complete_data_line(self):
    self.initialize()
    declared = "a-very-long-skill-name-that-remains-complete"
    self.write_skill(
        self.root / "skillsets/default/skills",
        "valid",
        f"name: {declared}\ndescription: valid",
    )

    colored = self.run_cli_tty("list", "-v", terminal_columns=20)

    self.assertEqual(colored.returncode, 0, colored.stderr)
    self.assertEqual(
        colored.stdout.splitlines()[1],
        "\x1b[2m  ---------|--------\x1b[0m",
    )
    self.assertEqual(len(colored.stdout.splitlines()), 3)
    self.assertIn(declared, colored.stdout.splitlines()[2])

    captured = self.run_cli("list", "-v")
    self.assertEqual(captured.returncode, 0, captured.stderr)
    self.assertEqual(
        captured.stdout.splitlines()[1],
        "  ---------|" + "-" * (len(declared) + 1),
    )
```

- [ ] **Step 3: Run the new tests and verify RED behavior**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_verbose_list_colorizes_independent_segments_only_for_eligible_tty \
  tests.test_skillset.SkillsetTests.test_verbose_list_tty_color_honors_environment_opt_outs \
  tests.test_skillset.SkillsetTests.test_verbose_list_caps_only_tty_separator_and_keeps_one_complete_data_line
```

Expected: nonzero exit because Task 1 emits no ANSI styles and does not cap the TTY separator. Data text must already
remain complete.

- [ ] **Step 4: Add segmented cell rendering and replace `render_verbose_list`**

Add the helper and replace Task 1's renderer with this final implementation:

```python
def render_skill_entries(entries, colored):
    if not entries:
        return styled("(no skills)", DIM, colored)
    rendered = []
    for display_name, annotation, reason in entries:
        if rendered:
            rendered.append(", ")
        if reason is None:
            rendered.append(styled(display_name, CYAN, colored))
            continue
        rendered.append(display_name + " ")
        code = YELLOW if reason == "missing description" else RED
        rendered.append(styled(annotation, code, colored))
    return "".join(rendered)


def render_verbose_list(rows, output):
    colored = color_enabled(output)
    skill_cells = [
        ", ".join(skill_entry_text(entry) for entry in entries)
        if entries
        else "(no skills)"
        for _active, _name, entries in rows
    ]
    left_width = max(display_width("SKILLSET"), *(display_width(row[1]) for row in rows))
    right_width = max(display_width("SKILLS"), *(display_width(cell) for cell in skill_cells))
    divider = styled("|", DIM, colored)
    header_left = styled("SKILLSET", BOLD, colored)
    header_left += " " * (left_width - display_width("SKILLSET"))
    print(f"  {header_left} {divider} {styled('SKILLS', BOLD, colored)}", file=output)
    separator = "  " + "-" * (left_width + 1) + "|" + "-" * (right_width + 1)
    width = terminal_width(output)
    if width is not None:
        separator = separator[:width]
    print(styled(separator, DIM, colored), file=output)
    for active, name, entries in rows:
        if active:
            marker = styled("*", BOLD + CYAN, colored) + " "
            left_cell = styled(name, BOLD + CYAN, colored)
        else:
            marker = "  "
            left_cell = name
        left_cell += " " * (left_width - display_width(name))
        print(
            f"{marker}{left_cell} {divider} {render_skill_entries(entries, colored)}",
            file=output,
        )
```

Padding and commas remain outside styles. The plain `skill_cells` list remains the sole source for width calculation.

- [ ] **Step 5: Run Task 2 GREEN tests and all verbose-list tests**

Run the Step 3 command, then:

```sh
python3 -m unittest discover -s tests -p 'test_skillset.py' -k verbose_list -v
```

Expected: both commands exit 0. Confirm the discovered run includes the plain contract, invalid-only, Unicode,
sanitization, styling, opt-out, and separator tests.

- [ ] **Step 6: Run adjacent `show` presentation tests to protect shared helpers**

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_show_prints_borderless_table_with_aligned_inner_delimiter \
  tests.test_skillset.SkillsetTests.test_show_caps_only_tty_separator_to_terminal_width \
  tests.test_skillset.SkillsetTests.test_show_colorizes_only_eligible_tty_output \
  tests.test_skillset.SkillsetTests.test_show_tty_color_honors_environment_opt_outs \
  tests.test_skillset.SkillsetTests.test_show_aligns_common_wide_and_combining_skill_names
```

Expected: five tests pass with exit code 0; `show` output remains unchanged.

- [ ] **Step 7: Review the diff and request permission before committing this checkpoint**

Run `jj diff -- tests/test_skillset.py lib/skillset/metadata.py`. Confirm styling occurs after sanitization and no `show`
body changed. If the user authorizes a commit, run:

```sh
jj commit -m "Add safe styling to verbose skillset listing"
```

---

### Task 3: Documentation, full verification, and bead handoff

**Files:**
- Modify: `README.md:113-159`
- Modify: `docs/specs/2026-07-10-named-skillsets-cli-design.md:136-145`
- Verify: `docs/specs/2026-07-11-skillset-list-verbose-output-design.md`

**Interfaces:**
- Consumes: the final CLI behavior from Tasks 1 and 2.
- Produces: user-facing examples and an updated durable inspection contract.

- [ ] **Step 1: Replace the README verbose-list example and explanation**

Use this content in the verbose-list subsection:

````markdown
Verbose output with either `-v` or `--verbose` uses an aligned inventory table.
Valid entries use declared skill names; malformed entries use their directory name
followed by `[invalid: REASON]`. A set with no inspectable entries shows `(no skills)`:

```text
$ skillset list --verbose
  SKILLSET   | SKILLS
  -----------|---------------------------------------------
* default    | alpha, broken [invalid: missing description]
  experiment | (no skills)
```
````

The literal example is already aligned for `experiment` as the ten-cell left-column maximum.

- [ ] **Step 2: Generalize the README color paragraph to cover both inspection tables**

Document that verbose `list` and `show` share TTY eligibility, bold headers, cyan valid names, yellow missing-description
annotations, red other invalid annotations, and dim delimiters/separators. Also state that verbose `list` highlights its
active marker/name in bold cyan and dims `(no skills)`, while pipes and redirects remain plain.

- [ ] **Step 3: Update the original named-skillsets inspection contract**

Replace its verbose-list bullet with:

```markdown
- `skillset list -v` and `skillset list --verbose` render a headered, aligned `SKILLSET | SKILLS` table with the active
  `* ` gutter. Each set's sorted valid names and invalid `DIRECTORY [invalid: REASON]` entries stay on one line; a truly
  empty inventory shows `(no skills)`. Automatic color is TTY-only and is suppressed by `NO_COLOR` and `TERM=dumb`.
```

- [ ] **Step 4: Run the full verification suite**

```sh
python3 -m unittest discover -s tests -v
```

Expected: exit code 0 with all tests passing and no unexpected stderr or resource warnings.

- [ ] **Step 5: Inspect final repository state and planning-term leakage**

Run:

```sh
grep -RInE 'phase|milestone|bead agents-7eo' \
  lib tests README.md docs/specs/2026-07-10-named-skillsets-cli-design.md || true
jj status
jj diff --stat
jj diff
```

Expected: no planning identifiers in production code, tests, README, or the durable original contract. The diff contains
only the approved implementation, tests, docs, the new spec/plan, and bead metadata. Do not revert unexpected user work;
stop and ask if unrelated changes appear.

- [ ] **Step 6: Request permission for the final commit and bead closure**

If the user authorizes a commit, run:

```sh
jj commit -m "Document verbose skillset inventory output"
```

After verification and only with explicit user approval, close and flush the tracker:

```sh
br close agents-7eo --reason="Completed"
br sync --flush-only
```

Report every verification command, exit code, test count, and any remaining working-copy changes. Stop after completing
bead `agents-7eo`; do not begin another bead automatically.