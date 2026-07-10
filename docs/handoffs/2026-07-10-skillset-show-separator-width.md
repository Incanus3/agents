# `skillset show` Separator-Width Handoff

## Checkpoint

The friendlier `skillset show` feature is implemented, reviewed, committed, and pushed. The next session should make one
small follow-up change: cap only the separator line to the current terminal width so a long description does not cause a
visually wrapped line of dashes.

- Ready issue: `agents-09y` — Cap skillset show separator to terminal width
- Latest feature commit: `a76b55bbbd34329c411dff0b5e2b0ff5fa1ae268` (`main` and `origin/main`)
- Feature design: `docs/specs/2026-07-10-skillset-show-output-design.md`
- Feature plan: `docs/plans/2026-07-10-skillset-show-output-implementation.md`
- Production formatter: `lib/skillset/metadata.py`
- Black-box and PTY tests: `tests/test_skillset.py`

At handoff creation, the repository was clean at commit `a76b55b` before creating `agents-09y`. The new bead record and
this handoff are intentionally uncommitted follow-up state. No production changes for separator capping have started.

## Latest verification

Immediately before commit and push, the complete suite passed:

```sh
python3 -m unittest discover -s tests -v
```

Result: 105 tests passed, exit status 0. Final independent review found no required changes. The pushed working copy was
clean, and local and remote `main` resolved to `a76b55b`.

## Current `show` behavior and invariants

- `skillset show` defaults to the active set; `skillset show NAME` inspects an explicit active or inactive set.
- Non-empty output is a borderless `SKILL | DESCRIPTION` table. Empty sets print `No skills installed.`.
- Valid names are cyan, headers bold, missing-description diagnostics yellow, other invalid diagnostics red, and table
  separators dim when stdout is an eligible TTY.
- ANSI styling is disabled for non-TTY output, when `NO_COLOR` is present, or when `TERM=dumb`.
- User-controlled text is sanitized with `printable_text` before generated ANSI styling is applied.
- Width calculation handles common combining and East Asian wide/full-width characters. Full descriptions are never
  truncated or wrapped by the program.
- Piped and redirected output is deterministic and fully represented; tests depend on its exact plain text.

Do not weaken these invariants while adding the separator cap.

## Approved follow-up behavior

The user explicitly chose separator-only capping. Do not truncate, wrap, abbreviate, or otherwise alter headers, skill
names, descriptions, or data rows.

1. Build the natural separator exactly as today.
2. If stdout is a TTY, query its current terminal column count immediately before rendering the separator.
3. If the detected width is positive, truncate the plain ASCII separator from the right to at most that many columns.
4. Apply the existing dim style after truncation, preserving one reset around the complete emitted separator.
5. Cap the separator for any TTY, even when ANSI color is disabled by `NO_COLOR` or `TERM=dumb`.
6. For pipes and redirects, emit the complete natural separator unchanged.
7. If width detection is unsupported, raises, or reports zero/nonpositive columns, emit the complete separator unchanged.

The point is solely to prevent a very long dash line from wrapping. A full description may still wrap naturally in the
terminal, which is desired.

## Recommended implementation

Keep the change local to the formatter. A small helper near `color_enabled` can return an optional positive terminal
width using `os.get_terminal_size(output.fileno()).columns`. It should first require `output.isatty()` and catch the
stream/descriptor errors expected from streams without a usable file descriptor.

The separator consists only of ASCII `-` and `|`, so slicing the unstyled string by the detected column count is safe.
Do not apply slicing after ANSI codes are present. If a terminal is narrower than the complete left segment, right-side
truncation will necessarily remove the junction; this rare case still satisfies the strict no-wrap requirement and does
not justify changing cell content.

No dependency or new CLI option is needed.

## Testing strategy

Use TDD and keep all HOME state isolated in the existing test fixture.

- Extend `run_cli_tty` with an optional terminal-column argument. Set PTY dimensions before spawning the child, using
  `TIOCSWINSZ`; keep its current default behavior for existing tests.
- Add a RED test with a long description and a narrow explicit PTY width. Verify the emitted separator's visible payload
  is exactly the terminal width and remains wrapped by the existing dim SGR sequence.
- In the same behavior test, verify the full description remains present and unchanged.
- Verify a TTY with `NO_COLOR` still caps the plain separator.
- Preserve or add an assertion that captured non-TTY output retains the complete natural separator.
- Preserve zero-width/default-PTY fallback behavior so existing PTY tests do not accidentally collapse the separator.
- Run the focused RED test, implement minimally, run all `test_show...` tests, then run the complete suite.

Likely files:

- `lib/skillset/metadata.py`
- `tests/test_skillset.py`
- `README.md` and the durable inspection spec only if the user-visible width behavior needs documenting

## Workflow and repository guidance

- Start with `br ready`, then claim only `agents-09y` with `br update agents-09y --status=in_progress`.
- Follow test-driven development: tests first, controller verifies RED, production change, controller verifies GREEN.
- If using subagents, do not let them run verification commands; run tests in the controller.
- Obtain a read-only task review and final review before closure.
- Close `agents-09y` and run `br sync --flush-only` after verified completion.
- Prefer Jujutsu. If any `jj` command reports that the working copy is stale, stop and ask the user to resolve it.
- Do not commit or push without explicit user permission.

## Fresh-session checklist

1. Read this handoff and `br show agents-09y`.
2. Confirm `jj status`; preserve any unexpected user changes.
3. Inspect `show`, `color_enabled`, and the PTY helper signatures before editing.
4. Claim `agents-09y`.
5. Add the narrow-PTY RED test and verify the expected failure.
6. Implement only separator capping and verify focused plus full tests.
7. Review, close, and sync the bead; stop at the bead checkpoint.

## Copy-ready resume prompt

```text
Continue the separator-width follow-up in /home/jakub/.agents.

Read docs/handoffs/2026-07-10-skillset-show-separator-width.md first, then inspect and claim ready bead agents-09y.
Follow the approved separator-only scope exactly: on a TTY, detect the current positive terminal width at render time and
truncate only the unstyled separator line from the right before applying dim styling. Keep full headers, names,
descriptions, and rows unchanged. Keep non-TTY output complete and deterministic; fall back to the full separator when
width detection fails or reports a nonpositive width. Cap TTY separators even under NO_COLOR or TERM=dumb.

Use TDD with an explicitly sized PTY, run verification in the controller, obtain task and final read-only reviews, then
close and sync agents-09y. Do not commit or push without explicit permission. Stop after this bead.
```
