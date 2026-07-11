# Friendlier `skillset list -v` Design

## Purpose

Make verbose skillset listing as readable and terminal-safe as `skillset show`. The command will render an aligned
two-column table, expose malformed skill entries instead of silently omitting them, and add restrained TTY-only color.
Plain `skillset list` remains unchanged.

This specification extends the inspection contract in
`docs/specs/2026-07-10-named-skillsets-cli-design.md` and follows the presentation conventions established by
`docs/specs/2026-07-10-skillset-show-output-design.md`.

## Repository context

- The dependency-free Python CLI is dispatched by `lib/skillset/cli.py`.
- `lib/skillset/metadata.py` implements `list_sets(root, verbose)` and `show(root, name, output=None)`.
- Verbose listing currently prints a tab followed by sorted valid declared skill names, uses `(no skills)` when no valid
  names exist, and omits malformed entries.
- `show` already provides terminal-cell width, TTY color detection, styling, and terminal-control sanitization helpers.
- Black-box integration coverage is in `tests/test_skillset.py`; captured stdout is non-interactive by default, and a
  pseudo-terminal helper covers interactive output.
- At design time the Jujutsu working copy had no pre-existing changes. Bead `agents-7eo` tracks implementation.

No external research or runtime dependency is needed.

## Command scope and compatibility

The accepted forms remain `skillset list`, `skillset list -v`, and `skillset list --verbose`. Both verbose flags are
equivalent. Argument parsing, layout validation, locking, error text, exit statuses, stderr behavior, and read-only
behavior do not change.

Non-verbose output remains byte-for-byte compatible: sets are printed in lexical name order, one per line, and only the
active set is prefixed with `* `. The change applies only to successful verbose output.

## Plain verbose output contract

Verbose output is a headered, borderless table with a fixed two-character active-state gutter:

```text
  SKILLSET | SKILLS
  ---------|---------------------------------------------
* default  | alpha, broken [invalid: missing description]
  empty    | (no skills)
```

The active row begins with `* `; inactive rows and both header lines begin with two spaces. `SKILLSET` and set names form
the left column. Its width is the maximum terminal-cell width of the header and sanitized set names. Header and data
rows contain one space on each side of `|`, and rows contain no trailing whitespace after the `SKILLS` cell.

The separator starts with the two-space gutter. Its left run contains enough dashes to cover the left column and the
space before `|`; its right run covers the space after `|` and the maximum display width of `SKILLS` or any complete
skills cell. Non-TTY output receives the full separator. On a TTY, only the separator is capped to the positive terminal
width, following current `show` behavior; headers and data are never truncated or wrapped.

Every successful verbose invocation ends with a newline. Redirected, piped, and captured output contains no ANSI
escapes and is independent of terminal width.

## Skill inventory contract

Each `SKILLS` cell is a comma-and-space-separated inventory. Entries are sorted lexically by their sanitized displayed
name, with the complete display text as a deterministic tie-breaker.

- A valid entry is its sanitized declared skill name.
- An invalid entry is `DIRECTORY [invalid: REASON]`, using the sanitized directory name and the existing inspection
  reason.
- `(no skills)` is used only when inspection yields no valid or invalid skill-directory entries. Ignored ordinary files
  do not prevent this state.

Thus a set containing only malformed skill directories no longer appears empty. Metadata parsing, candidate filtering,
invalid classifications, symlink handling, and terminal-control escaping remain unchanged.

Each skillset occupies exactly one physical output line, even when its inventory exceeds the terminal width. There is no
ellipsis, continuation row, or terminal-dependent data transformation.

## Display width and sanitization

Alignment is calculated from sanitized plain text before styling. Existing `display_width` semantics remain authoritative:
combining characters occupy zero cells, East Asian `W` and `F` characters occupy two, and other printable characters
occupy one. Exact grapheme width for every emoji sequence remains out of scope.

Set names, declared names, and invalid directory names pass through `printable_text` before width calculation or output.
Inspection reasons are fixed program text. Generated ANSI escapes are applied only after sanitization.

## Interactive color contract

Color is enabled only when stdout is a TTY, `NO_COLOR` is absent, and `TERM` is not `dumb`. No color-control option is
added.

When enabled:

- both header cells are bold;
- the active `*` marker and active set name are bold cyan;
- valid declared skill names are cyan;
- invalid directory names remain plain;
- `[invalid: missing description]` is yellow;
- every other invalid annotation is red;
- comma separators remain plain;
- each row's `|` and the complete header separator are dim;
- `(no skills)` is dim.

Each styled segment resets at its own boundary. Styles must not leak into padding, punctuation, adjacent entries, or
following output. Color changes presentation only and does not alter sorting, width calculation, or diagnostics.

## Implementation design and future extraction seam

Use a list-specific renderer in `lib/skillset/metadata.py`; do not refactor working `show` rendering or introduce a new
module in this change. Reuse the existing width, sanitization, color-policy, terminal-width, and styling primitives.

Keep the implementation in three distinct stages:

1. collect structured skillset and inspected-entry records;
2. derive sanitized plain cell text, styleable segments, ordering, and display widths;
3. render the verbose table to an output stream.

`list_sets` gains an optional output stream defaulting to `sys.stdout`, matching `show` and improving direct formatter
testability without changing CLI dispatch semantics. Plain and styled forms must derive from the same structured rows.
ANSI assembly must not occur during filesystem traversal or metadata parsing.

Representing cells as plain display text plus independently styleable segments is the intended seam for a later move to
a dedicated terminal-rendering module. This change deliberately accepts a small amount of table-scaffold duplication to
avoid coupling a generic abstraction to only two current callers.

## Expected file boundaries

- `lib/skillset/metadata.py`: collect verbose rows, format the table, and apply optional styling.
- `tests/test_skillset.py`: replace the tab-separated contract and add alignment, invalid-entry, Unicode, TTY, opt-out,
  long-row, separator-width, and compatibility coverage.
- `README.md`: replace the verbose example and document invalid entries and automatic color behavior.
- `docs/specs/2026-07-10-named-skillsets-cli-design.md`: update the superseded verbose-list contract.

`lib/skillset/cli.py` should require no semantic change. No package, lockfile, or runtime dependency is added.

## Verification strategy

Tests must establish:

1. `-v` and `--verbose` produce the exact approved plain table.
2. Non-verbose `list` retains its exact existing output.
3. Set rows and mixed valid/invalid entries use the specified ordering and wording.
4. Truly empty inventories print `(no skills)`, while invalid-only inventories show their entries.
5. Common wide and combining Unicode values align by terminal cells.
6. User-controlled terminal characters are visibly escaped before styling.
7. Long inventories remain one physical data line and are not truncated.
8. A pseudo-terminal receives the specified segment-level styles and dim delimiter/separator.
9. `NO_COLOR` and `TERM=dumb` independently suppress all ANSI escapes in a pseudo-terminal.
10. Only a TTY separator is capped to terminal width; redirected output retains the full separator.
11. Existing malformed metadata, symlink safety, locking, and strictly read-only inspection tests continue to pass.

Write or update focused tests before production code. Run the smallest verbose-list tests while iterating, then execute:

```bash
python3 -m unittest discover -s tests -v
```

Final reporting must include the commands, exit codes, and relevant test counts.

## Rejected alternatives and trade-offs

- Stacked skillset groups handle long names well but produce substantially more output.
- A count column improves inventory summaries but widens the table and adds information not requested here.
- Wrapping at item boundaries improves narrow-terminal scanning but creates terminal-dependent continuation rules.
- Ellipsis preserves width but hides installed or malformed entries.
- Keeping tab-separated output is compact but does not align predictably and cannot present the requested hierarchy.
- A shared generic renderer or dedicated terminal module could reduce future duplication, but refactoring `show` broadens
  risk now. The structured-row and segment boundary preserves that later option.
- A third-party table or color library is disproportionate to this fixed output and violates the dependency-free design.

## Implementation checklist

1. Claim bead `agents-7eo` and add failing black-box tests for the exact plain contract.
2. Add invalid-only, ordering, Unicode, long-line, TTY color, opt-out, and separator-width tests.
3. Implement structured row collection and the list-specific renderer without changing non-verbose output.
4. Update README and the original inspection contract.
5. Run focused tests, then the complete suite, and inspect the final Jujutsu diff.
6. Keep any unrelated working-copy changes untouched and report them separately.