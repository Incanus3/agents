# Transactional CLI Safety Guide

Load this guide when designing, implementing, testing, or reviewing CLIs that mutate filesystem state, perform rollback,
delegate transparently to another process, or retain locks and other resources across process boundaries.

## Test both sides of side-effecting boundaries

For filesystem and process operations, cover failures at each materially different state boundary:

- Before the syscall changes state
- Immediately after the syscall changes state
- During rollback or cleanup
- After the operation has effectively committed

Fault injection should wrap the real operation when testing post-syscall behavior. Verify the resulting filesystem or
process state as well as the exact command outcome. A generic nonzero-status assertion is insufficient when a signal,
committed success, or a particular operational failure has distinct semantics.

For multi-step transactions, write down the valid states before implementation. Recovery should either restore a known
valid state or report the concrete paths that contain the remaining data.

## Treat transaction markers as persistent state

Staging paths, intent files, temporary symlinks, and similar markers participate in the state model even when they are
normally short-lived. Include them in:

- Initialization and adoption preflight
- Normal layout validation
- Recovery diagnostics
- Version-control ignores when they can appear in the repository

Do not silently remove an unknown or noncanonical marker. Report its exact path and preserve it for diagnosis. Cleanup
may remove only a marker whose type, location, and target match the operation's canonical expectations.

## Preserve transparent delegation boundaries

A wrapper that delegates to another CLI should preserve upstream arguments and behavior unless a documented safety rule
requires a change:

- Treat `--` as the end of wrapper-relevant options.
- Do not consume upstream `-h`, `--help`, or future options.
- Preserve argument order, empty arguments, and token boundaries exactly.
- Inject wrapper-required options only before `--`.
- Interpret only explicitly supported upstream commands and flags.
- Preserve standard streams, signals, and exit status.
- Apply environment changes to a copied child environment, not the caller.

Test delegation with a local fake executable rather than network access. Record exact arguments and environment metadata,
and synchronize process tests with marker files or locks rather than fixed sleeps.

## Make resource ownership unambiguous

Every file descriptor, lock, process, temporary path, and cleanup action should have one clear owner.

- Transfer descriptor ownership explicitly; do not leave both layers responsible for closing it.
- Keep locks for the full protected lifetime, including delegated child execution when required.
- On failed process replacement, release resources through the normal unwind path.
- Never clean up a path merely because its name resembles a temporary path; validate canonical ownership first.
- Ensure cleanup errors cannot hide the location of the only remaining data copy.

Review exception and interrupt paths separately. `KeyboardInterrupt`, post-syscall exceptions, and ordinary pre-syscall
errors can represent different committed states even when they arise from the same source line.