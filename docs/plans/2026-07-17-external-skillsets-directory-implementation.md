# External Skillsets Directory Implementation

**Date:** 2026-07-17
**Specification:** `docs/specs/2026-07-17-external-skillsets-directory-design.md`

## Scope

Implement the approved optional `config.json` contract without changing
unconfigured installations.

## Steps

1. Add strict config parsing and canonical skillsets-container validation in
   `layout.py`.
2. Use the new validator from normal layout validation and safe-repair
   discovery.
3. Extend initialization to create and transactionally roll back the configured
   top-level link.
4. Teach doctor to validate config and the authorized link before traversing
   skillsets.
5. Add black-box tests for valid configuration, failure boundaries, doctor
   behavior, and backward compatibility.
6. Document setup and migration in `README.md`.
7. Run the focused tests and then the complete unittest suite.

## Review checklist

- No configured path is followed before its config and link are validated.
- Rollback never removes the configured external directory.
- Existing error text and behavior remain stable when config is absent.
- Named sets and skills remain real directories.
- Inspection commands remain read-only.
- Tests cover post-symlink and post-set-creation failures.
