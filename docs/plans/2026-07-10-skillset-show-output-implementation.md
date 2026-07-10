# Friendlier `skillset show` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `skillset show` default to the active set and render safe, aligned, colorized terminal output.

**Architecture:** Keep metadata inspection unchanged, but convert its results into structured display rows before
rendering. A small standard-library formatter will measure Unicode display cells, produce deterministic plain tables,
and add ANSI styles only after sanitization when stdout is an eligible TTY.

**Source of truth:** `docs/specs/2026-07-10-skillset-show-output-design.md`
**Tracking:** `agents-zgu`
**Tech stack:** Python 3 standard library, argparse, ANSI SGR sequences, Linux pseudo-terminals, and unittest subprocess
tests.

## Global constraints

- Preserve existing full-layout and explicit-set validation, locking, read-only behavior, errors, and exit statuses.
- Emit color only when stdout is a TTY, `NO_COLOR` is absent, and `TERM` is not `dumb`.
- Sanitize every user-controlled value with `printable_text` before adding generated ANSI sequences.
- Use no third-party dependency and add no color-control CLI flags.
- Keep `skillset doctor` classifications unchanged; yellow for `missing description` is presentation-only.
- Do not add outer table borders or trailing whitespace after final cells.
- Do not touch the unrelated `skillsets/minimal/.skill-lock.json` working-copy change.
- Do not commit without explicit user permission.

---

### Task 1: Optional selection and deterministic plain table

**Files:**
- Modify: `tests/test_skillset.py:172-176, 941-975, 1078-1319`
- Modify: `lib/skillset/cli.py:58-59`
- Modify: `lib/skillset/metadata.py:240-252`

**Interfaces:**
- Consumes: `validate_layout(root) -> str`, `validate_set(root, name) -> Path`, `inspect_skills(skills) -> list[tuple]`,
  and `printable_text(value) -> str`.
- Produces: `display_width(value: str) -> int`, `pad_display(value: str, width: int) -> str`, and
  `show(root: Path, name: str | None, output: TextIO | None = None) -> None`.
- Preserves: `inspect_skills`, metadata parsing, sorting by sanitized displayed name, and explicit-name validation.

- [ ] **Step 1: Add RED tests for optional selection and exact empty output**

Change the empty test expectation and add a test that distinguishes active and explicit sets:

```python
def test_show_empty_set_prints_explanatory_message(self):
    self.initialize()
    result = self.run_cli("show")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout, "No skills installed.\n")
    self.assertEqual(result.stderr, "")

def test_show_defaults_to_active_set_and_explicit_name_overrides_it(self):
    self.initialize("default")
    alternate = self.make_set(self.root, "alternate")
    self.write_skill(self.root / "skillsets/default/skills", "alpha", "name: alpha\ndescription: active")
    self.write_skill(alternate / "skills", "beta", "name: beta\ndescription: explicit")
    active = self.run_cli("show")
    explicit = self.run_cli("show", "alternate")
    switched = self.run_cli("use", "alternate")
    new_active = self.run_cli("show")
    self.assertIn("alpha", active.stdout)
    self.assertNotIn("beta", active.stdout)
    self.assertIn("beta", explicit.stdout)
    self.assertNotIn("alpha", explicit.stdout)
    self.assertEqual(switched.returncode, 0, switched.stderr)
    self.assertIn("beta", new_active.stdout)
    self.assertNotIn("alpha", new_active.stdout)
```

Also add a focused help assertion:

```python
def test_show_help_marks_name_as_optional(self):
    result = self.run_cli("show", "--help")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertRegex(result.stdout, r"usage: skillset show \[-h\] \[name\]")
```

- [ ] **Step 2: Add RED tests for exact table layout and Unicode display width**

Add one ASCII contract test and one display-cell test:

```python
def test_show_prints_borderless_table_with_aligned_inner_delimiter(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    self.write_skill(skills, "short", "name: alpha\ndescription: Short")
    self.write_skill(skills, "long", "name: longer-name\ndescription: Longer description")
    result = self.run_cli("show")
    self.assertEqual(result.stdout,
        "SKILL       | DESCRIPTION\n"
        "------------|-------------------\n"
        "alpha       | Short\n"
        "longer-name | Longer description\n")
    self.assertNotIn("\x1b", result.stdout)

def test_show_aligns_common_wide_and_combining_skill_names(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    self.write_skill(skills, "wide", "name: 界界界\ndescription: wide")
    combining = "e\u0301" * 6
    self.write_skill(skills, "combining", f"name: {combining}\ndescription: combining")
    result = self.run_cli("show")
    self.assertEqual(result.stdout,
        "SKILL  | DESCRIPTION\n"
        "-------|------------\n"
        f"{combining} | combining\n"
        "界界界 | wide\n")
```

- [ ] **Step 3: Update existing show assertions to the new row structure before implementation**

Replace the old em-dash-specific helper with a table-row parser:

```python
def show_rows(self, output):
    lines = output.splitlines()
    self.assertGreaterEqual(len(lines), 2, output)
    self.assertIn("|", lines[0])
    return [tuple(cell.strip() for cell in line.split("|", 1)) for line in lines[2:]]

def assert_invalid_show_entry(self, output, directory, category):
    matches = [row for row in self.show_rows(output) if row[0] == directory]
    self.assertEqual(len(matches), 1, (directory, output))
    self.assertIn(category.lower(), matches[0][1].lower())
```

Update the complete workflow's empty `shown.stdout` expectation to `No skills installed.\n`. In scalar, escaping,
malformed, and symlink tests, assert data through `show_rows`; preserve exact checks for escaped controls and all invalid
siblings. Compute sorting from `[row[0] for row in self.show_rows(result.stdout)]` instead of splitting on ` — `.

Use these exact row-level assertions where the old delimiter appeared:

```python
self.assertEqual(self.show_rows(result.stdout), [
    ("alpha", "plain description"),
    ("comments", "plain value"),
    ("double", 'first second "quoted" and \\ slash'),
    ("folded", "folded line next line"),
    ("literal", "first line second line"),
    ("multi-double", "first double line second line"),
    ("multi-plain", "first plain line second plain line"),
    ("multi-single", "first single line second single line"),
    ("o'brien", "single 'quoted' description"),
    ("quoted-comment", "kept # hash"),
])

self.assertEqual(self.show_rows(result.stdout), [
    (r"café\x1b\x7f\u202eoutil", r"naïve\x1b\x9b\u2066 texte"),
])

self.assertIn(("valid", "direct real directory"), self.show_rows(result.stdout))
displayed = [row[0] for row in self.show_rows(result.stdout)]
self.assertEqual(displayed, sorted(displayed))
```

- [ ] **Step 4: Run focused tests to verify RED behavior**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_show_empty_set_prints_explanatory_message \
  tests.test_skillset.SkillsetTests.test_show_defaults_to_active_set_and_explicit_name_overrides_it \
  tests.test_skillset.SkillsetTests.test_show_help_marks_name_as_optional \
  tests.test_skillset.SkillsetTests.test_show_prints_borderless_table_with_aligned_inner_delimiter \
  tests.test_skillset.SkillsetTests.test_show_aligns_common_wide_and_combining_skill_names
```

Expected: failures show that `name` is required, empty output is blank, and em-dash rows are not tabular. Setup commands
must still succeed; failures must not indicate filesystem mutation or validation regressions.

- [ ] **Step 5: Make `name` optional without bypassing validation**

Change only the show parser declaration:

```python
show_parser = commands.add_parser("show", help="show skills in a skillset")
show_parser.add_argument("name", nargs="?")
```

Dispatch remains `show(root, arguments.name)` so metadata rendering owns active-name resolution.

- [ ] **Step 6: Implement structured plain rendering and display-cell padding**

Add `sys` to metadata imports and introduce these helpers immediately before `show`:

```python
def display_width(value):
    width = 0
    for character in value:
        if unicodedata.combining(character):
            continue
        width += 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
    return width


def pad_display(value, width):
    return value + " " * (width - display_width(value))
```

Replace `show` with structured row construction and plain rendering. Keep `output=None` to avoid binding stdout at
import time:

```python
def show(root, name, output=None):
    output = sys.stdout if output is None else output
    active_name = validate_layout(root)
    selected_name = active_name if name is None else name
    skills = validate_set(root, selected_name) / "skills"
    rows = []
    for directory, declared, description, reason in inspect_skills(skills):
        left = printable_text(declared if reason is None else directory)
        right = printable_text(description) if reason is None else f"[invalid: {reason}]"
        rows.append((left, right, reason))
    rows.sort(key=lambda row: (row[0], row[1]))
    if not rows:
        print("No skills installed.", file=output)
        return
    left_width = max(display_width("SKILL"), *(display_width(row[0]) for row in rows))
    right_width = max(display_width("DESCRIPTION"), *(display_width(row[1]) for row in rows))
    print(f"{pad_display('SKILL', left_width)} | DESCRIPTION", file=output)
    print("-" * (left_width + 1) + "|" + "-" * (right_width + 1), file=output)
    for left, right, _reason in rows:
        print(f"{pad_display(left, left_width)} | {right}", file=output)
```

The invalid reason strings originate internally, but keeping the complete right cell construction after directory
sanitization preserves the existing one-line output contract.

- [ ] **Step 7: Run focused GREEN verification and show regressions**

Run the Step 4 command, then:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_show_parses_supported_frontmatter_scalars_and_normalizes_descriptions \
  tests.test_skillset.SkillsetTests.test_show_visibly_escapes_metadata_terminal_controls \
  tests.test_skillset.SkillsetTests.test_show_reports_malformed_frontmatter_without_hiding_valid_siblings \
  tests.test_skillset.SkillsetTests.test_show_ignores_regular_files_and_never_follows_direct_skill_symlinks
```

Expected: all listed tests pass, both commands exit 0, control bytes remain escaped, and invalid siblings remain visible.

---

### Task 2: Safe automatic TTY styling

**Files:**
- Modify: `tests/test_skillset.py:1-82, show test section after line 1078`
- Modify: `lib/skillset/metadata.py` beside the Task 1 formatting helpers and `show`

**Interfaces:**
- Consumes: Task 1's structured `(left, right, reason)` rows and `output` stream.
- Produces: `color_enabled(output: TextIO) -> bool` and `styled(value: str, code: str, enabled: bool) -> str`.
- Preserves: byte-for-byte plain output when styling is disabled.

- [ ] **Step 1: Add a pseudo-terminal subprocess helper**

Import `errno` and add this helper beside `run_cli`:

```python
def run_cli_tty(self, *arguments, extra_environment=None):
    environment = self.environment()
    environment.pop("NO_COLOR", None)
    environment["TERM"] = "xterm-256color"
    if extra_environment:
        environment.update(extra_environment)
    master, slave = os.openpty()
    process = subprocess.Popen(
        [str(SKILLSET), *arguments], cwd=self.home, env=environment,
        stdout=slave, stderr=subprocess.PIPE, text=False,
    )
    os.close(slave)
    chunks = []
    try:
        while True:
            try:
                chunk = os.read(master, 4096)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            chunks.append(chunk)
        _stdout, stderr = process.communicate(timeout=5)
    finally:
        os.close(master)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
    stdout = b"".join(chunks).decode("utf-8").replace("\r\n", "\n")
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr.decode("utf-8"))
```

- [ ] **Step 2: Add RED tests for styles, severity colors, and opt-outs**

Create valid, missing-description, and missing-file rows, then assert generated styles:

```python
def test_show_colorizes_only_eligible_tty_output(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    self.write_skill(skills, "valid", "name: alpha\ndescription: valid")
    self.write_skill(skills, "warning", "name: warning")
    (skills / "error").mkdir()
    colored = self.run_cli_tty("show")
    self.assertEqual(colored.returncode, 0, colored.stderr)
    self.assertIn("\x1b[1mSKILL\x1b[0m", colored.stdout)
    self.assertIn("\x1b[2m|\x1b[0m", colored.stdout)
    self.assertRegex(colored.stdout, r"\x1b\[2m-+\|-+\x1b\[0m")
    self.assertIn("\x1b[36malpha\x1b[0m", colored.stdout)
    self.assertIn("\x1b[33m[invalid: missing description]\x1b[0m", colored.stdout)
    self.assertIn("\x1b[31m[invalid: missing SKILL.md]\x1b[0m", colored.stdout)
    plain = self.run_cli("show")
    self.assertNotIn("\x1b", plain.stdout)
```

Add exact opt-out and empty-state tests:

```python
def test_show_tty_color_honors_environment_opt_outs(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    self.write_skill(skills, "valid", "name: alpha\ndescription: valid")
    plain = self.run_cli("show").stdout
    for extra_environment in ({"NO_COLOR": "1"}, {"TERM": "dumb"}):
        with self.subTest(environment=extra_environment):
            result = self.run_cli_tty("show", extra_environment=extra_environment)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, plain)
            self.assertNotIn("\x1b", result.stdout)

def test_show_dims_empty_tty_message(self):
    self.initialize()
    result = self.run_cli_tty("show")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertEqual(result.stdout, "\x1b[2mNo skills installed.\x1b[0m\n")
```

Add a TTY-specific injection regression that distinguishes user input from generated SGR escapes:

```python
def test_show_sanitizes_terminal_controls_before_tty_styling(self):
    self.initialize()
    skills = self.root / "skillsets/default/skills"
    declared = "unsafe\x1b]8;;https://example.invalid\x07name"
    self.write_skill(skills, "unsafe", f"name: {declared}\ndescription: controlled")
    result = self.run_cli_tty("show")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertNotIn("\x1b]8;;", result.stdout)
    self.assertIn(r"unsafe\x1b]8;;https://example.invalid\x07name", result.stdout)
```

- [ ] **Step 3: Run the TTY tests to verify RED behavior**

Run:

```sh
python3 -m unittest -v \
  tests.test_skillset.SkillsetTests.test_show_colorizes_only_eligible_tty_output \
  tests.test_skillset.SkillsetTests.test_show_tty_color_honors_environment_opt_outs \
  tests.test_skillset.SkillsetTests.test_show_dims_empty_tty_message \
  tests.test_skillset.SkillsetTests.test_show_sanitizes_terminal_controls_before_tty_styling
```

Expected: failures because eligible TTY output contains no SGR sequences. PTY capture itself must complete without a
timeout and return status 0.

- [ ] **Step 4: Add isolated ANSI policy helpers**

Define constants and helpers near `display_width`:

```python
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
CYAN = "\x1b[36m"
YELLOW = "\x1b[33m"
RED = "\x1b[31m"


def color_enabled(output):
    return output.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def styled(value, code, enabled):
    return f"{code}{value}{RESET}" if enabled else value
```

- [ ] **Step 5: Apply styles after width calculation and sanitization**

In `show`, calculate `colored = color_enabled(output)` after selecting `output`. Keep Task 1's row text and widths
unchanged. Replace only the print section with:

```python
if not rows:
    print(styled("No skills installed.", DIM, colored), file=output)
    return
header_left = styled("SKILL", BOLD, colored) + " " * (left_width - display_width("SKILL"))
header_right = styled("DESCRIPTION", BOLD, colored)
divider = styled("|", DIM, colored)
print(f"{header_left} {divider} {header_right}", file=output)
separator = "-" * (left_width + 1) + "|" + "-" * (right_width + 1)
print(styled(separator, DIM, colored), file=output)
for left, right, reason in rows:
    left_cell = styled(left, CYAN, colored) if reason is None else left
    left_cell += " " * (left_width - display_width(left))
    if reason == "missing description":
        right_cell = styled(right, YELLOW, colored)
    elif reason is not None:
        right_cell = styled(right, RED, colored)
    else:
        right_cell = right
    print(f"{left_cell} {divider} {right_cell}", file=output)
```

Do not style padding or valid descriptions. Every generated style wraps one structural element or cell and resets before
the next element.

- [ ] **Step 6: Run TTY and plain-output GREEN verification**

Run the Step 3 command, then all tests whose names start with `test_show`:

```sh
python3 -m unittest -v -k show tests.test_skillset.SkillsetTests
```

Expected: every selected `test_show...` line is `ok`, the run ends with `OK`, and the command exits 0.

---

### Task 3: User documentation and complete verification

**Files:**
- Modify: `README.md:139-155`
- Modify: `docs/specs/2026-07-10-named-skillsets-cli-design.md:136-144`
- Verify: `lib/skillset/cli.py`, `lib/skillset/metadata.py`, `tests/test_skillset.py`

**Interfaces:**
- Consumes: the exact CLI behavior delivered by Tasks 1 and 2.
- Produces: user-facing usage and durable inspection-contract documentation.
- Preserves: terminology independent of internal beads or implementation stages.

- [ ] **Step 1: Update README examples and color explanation**

Replace the old show example with an omitted-name example using the approved table:

```text
$ skillset show
SKILL            | DESCRIPTION
-----------------|-------------------------------
alpha            | First skill
broken-directory | [invalid: missing description]
```

State that `NAME` is optional and defaults to the active skillset, while an explicit name inspects another set. Document
`No skills installed.` for empty sets. Explain that TTY output uses color, while pipes, redirects, `NO_COLOR`, and
`TERM=dumb` produce plain text.

- [ ] **Step 2: Update the original inspection contract**

Replace its `skillset show NAME` bullet with a concise pointer-compatible contract: `NAME` is optional and defaults to
the active set; non-empty output is the headered, aligned `SKILL | DESCRIPTION` table; empty output is
`No skills installed.`; invalid entries remain visible; automatic color never enters non-TTY output.

- [ ] **Step 3: Run complete verification**

Run:

```sh
python3 -m unittest discover -s tests -v
```

Expected: all tests pass, output ends with `OK`, and exit status is 0.

- [ ] **Step 4: Perform manual plain and interactive smoke tests**

Run plain capture against the managed test fixture through the automated tests, then run `skillset show` in a terminal.
Confirm visually that columns align, only inner borders appear, every `|` and the separator line are dim, missing
description is yellow, more severe invalid entries are red, valid names are cyan, and the header is bold. Do not mutate
the active set during this smoke check.

- [ ] **Step 5: Review scope and safety**

Run:

```sh
jj diff --git -- lib/skillset/cli.py lib/skillset/metadata.py tests/test_skillset.py README.md \
  docs/specs/2026-07-10-named-skillsets-cli-design.md
```

Confirm there are no raw user-controlled ANSI sequences, no dependency changes, no planning terminology in product
surfaces, and no edits to `skillsets/minimal/.skill-lock.json`. Request a read-only code review before completion.

- [ ] **Step 6: Close the bead checkpoint**

After review passes, close `agents-zgu`, run `br sync --flush-only`, report focused and full-suite evidence, encourage the
user to commit the changes, and stop. Do not create a commit without explicit permission.
