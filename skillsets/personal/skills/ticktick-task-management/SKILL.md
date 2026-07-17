---
name: ticktick-task-management
description: Use when managing TickTick projects and tasks.
---

# TickTick Task Management

Self-contained TickTick skill using the bundled `ticktick_cli.py` script.

## When to Use

Use this skill when the user wants to:
- list TickTick projects
- list tasks in a project
- create, move, update, complete, reopen, or delete a task
- work from this machine without exposing TickTick credentials

Do not use this skill for restoring tasks from trash; that did not work with the official API-token path tested here.

## Auth and Safety

- Read the token from `~/.config/ticktick.env`
- Expect `TICKTICK_API_TOKEN=...` in that file
- Never ask the user to paste the token into chat
- Never pass the token on the command line
- Prefer read-only commands first unless the user asked for a write

## Getting the API Token

Preferred local setup path:
- open the TickTick web app in the browser
- go to Settings → Account → API Keys
- copy the personal API token shown in the UI
- save it into `~/.config/ticktick.env` as `TICKTICK_API_TOKEN=...`

If the UI wording changes, the important part is: use the token exposed by the TickTick web app settings, not browser cookies or app session storage.

Quick setup example:
- `mkdir -p ~/.config`
- create `~/.config/ticktick.env`
- add one line: `TICKTICK_API_TOKEN=your-token-here`
- set restrictive permissions if needed: `chmod 600 ~/.config/ticktick.env`

## Bundled Files

- `ticktick_cli.py` — CLI implementation
- `test_ticktick_cli.py` — unit tests for the bundled CLI

## Commands

- `python ticktick_cli.py projects`
- `python ticktick_cli.py tasks --project <projectId>`
- `python ticktick_cli.py create --title "Task title" [--project <projectId>]`
- `python ticktick_cli.py move --task <taskId> --from-project <src> --to-project <dst>`
- `python ticktick_cli.py update --task <taskId> --project <projectId> [--title ...] [--content ...] [--priority N] [--due RFC3339]`
- `python ticktick_cli.py done --task <taskId> --project <projectId>`
- `python ticktick_cli.py reopen --task <taskId> --project <projectId>`
- `python ticktick_cli.py delete --task <taskId> --project <projectId>`
- add `--json` before the subcommand for structured output

## Verified Behavior

Confirmed against the official Open API token path:
- list projects works
- list tasks via `/project/{id}/data` works
- create works
- move works for normal tasks
- update works
- complete works
- reopen works by updating `status: 0`
- delete behaves as soft-delete to trash

Not supported in the tested path:
- restore / undelete from trash
- relying on top-level `GET /task` for general listing

## Workflow

1. Run `projects` to find the project ID.
2. Run `tasks --project <id>` to find the task ID.
3. Perform the requested mutation.
4. For reopen, use the built-in `reopen` command rather than crafting payloads manually.

## Verification

From this skill directory:
- `python test_ticktick_cli.py`
- `python ticktick_cli.py --help`

If a live smoke check is needed, prefer a read-only command first.
