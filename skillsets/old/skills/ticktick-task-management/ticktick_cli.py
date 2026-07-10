import argparse
import json
import sys
import urllib.request
from pathlib import Path

ENV_PATH = Path.home() / ".config" / "ticktick.env"
BASE_URL = "https://api.ticktick.com/open/v1"


def load_api_token(env_path=ENV_PATH):
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if key == "TICKTICK_API_TOKEN":
                return value.strip()
    raise RuntimeError(f"TICKTICK_API_TOKEN missing in {env_path}")


class TickTickClient:
    def __init__(self, token, opener=urllib.request.urlopen, base_url=BASE_URL):
        self.token = token
        self.opener = opener
        self.base_url = base_url.rstrip("/")

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ticktick-cli/0.1",
            },
        )
        with self.opener(req, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else None

    def list_projects(self): return self.request("GET", "/project")
    def get_project_data(self, project_id): return self.request("GET", f"/project/{project_id}/data")
    def get_task(self, project_id, task_id): return self.request("GET", f"/project/{project_id}/task/{task_id}")
    def create_task(self, payload): return self.request("POST", "/task", payload)
    def move_task(self, from_project_id, to_project_id, task_id):
        return self.request("POST", "/task/move", [{"fromProjectId": from_project_id, "toProjectId": to_project_id, "taskId": task_id}])
    def update_task(self, task_id, payload): return self.request("POST", f"/task/{task_id}", payload)
    def complete_task(self, project_id, task_id): return self.request("POST", f"/project/{project_id}/task/{task_id}/complete")
    def delete_task(self, project_id, task_id): return self.request("DELETE", f"/project/{project_id}/task/{task_id}")


def build_parser():
    parser = argparse.ArgumentParser(description="TickTick CLI")
    parser.add_argument("--json", action="store_true", dest="json_output")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("projects")
    p = sub.add_parser("tasks"); p.add_argument("--project", required=True)
    p = sub.add_parser("create"); p.add_argument("--title", required=True); p.add_argument("--project"); p.add_argument("--content"); p.add_argument("--priority", type=int); p.add_argument("--due")
    p = sub.add_parser("move"); p.add_argument("--task", required=True); p.add_argument("--from-project", required=True); p.add_argument("--to-project", required=True)
    p = sub.add_parser("update"); p.add_argument("--task", required=True); p.add_argument("--project", required=True); p.add_argument("--title"); p.add_argument("--content"); p.add_argument("--priority", type=int); p.add_argument("--due")
    for name in ("done", "reopen", "delete"):
        p = sub.add_parser(name); p.add_argument("--task", required=True); p.add_argument("--project", required=True)
    return parser


def parse_args(argv=None):
    return build_parser().parse_args(argv)


def _emit(stdout, payload, json_output, fallback):
    stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n" if json_output else fallback + "\n")


def _update_payload(task, args, status=None):
    payload = {
        "id": task["id"], "projectId": task["projectId"], "title": task.get("title"), "content": task.get("content", ""),
        "priority": task.get("priority", 0), "timeZone": task.get("timeZone"), "isAllDay": task.get("isAllDay", False),
    }
    if getattr(args, "title", None) is not None: payload["title"] = args.title
    if getattr(args, "content", None) is not None: payload["content"] = args.content
    if getattr(args, "priority", None) is not None: payload["priority"] = args.priority
    if getattr(args, "due", None) is not None: payload["dueDate"] = args.due
    if status is not None: payload["status"] = status
    return payload


def run_command(args, client, stdout=sys.stdout, json_output=None):
    json_output = args.json_output if json_output is None else json_output
    if args.command == "projects":
        data = client.list_projects(); _emit(stdout, data, json_output, "\n".join(f"{p['id']}\t{p['name']}" for p in data)); return
    if args.command == "tasks":
        data = client.get_project_data(args.project); tasks = data.get("tasks", []); _emit(stdout, tasks, json_output, "\n".join(f"{t['id']}\t{t['title']}" for t in tasks)); return
    if args.command == "create":
        payload = {"title": args.title}
        if args.project: payload["projectId"] = args.project
        if args.content: payload["content"] = args.content
        if args.priority is not None: payload["priority"] = args.priority
        if args.due: payload["dueDate"] = args.due
        data = client.create_task(payload); _emit(stdout, data, json_output, f"created {data.get('id', '')} {data.get('title', args.title)}"); return
    if args.command == "move":
        data = client.move_task(args.from_project, args.to_project, args.task); _emit(stdout, data, json_output, f"moved {args.task} to {args.to_project}"); return
    if args.command == "update":
        current = client.get_task(args.project, args.task); data = client.update_task(args.task, _update_payload(current, args)); _emit(stdout, data, json_output, f"updated {args.task}"); return
    if args.command == "done":
        data = client.complete_task(args.project, args.task); _emit(stdout, data, json_output, f"completed {args.task}"); return
    if args.command == "reopen":
        current = client.get_task(args.project, args.task); data = client.update_task(args.task, _update_payload(current, args, status=0)); _emit(stdout, data, json_output, f"reopened {args.task}"); return
    if args.command == "delete":
        data = client.delete_task(args.project, args.task); _emit(stdout, data, json_output, f"deleted {args.task} to trash"); return
    raise SystemExit(f"unknown command: {args.command}")


def main(argv=None):
    args = parse_args(argv)
    client = TickTickClient(load_api_token())
    run_command(args, client)


if __name__ == "__main__":
    main()
