import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "ticktick_cli.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ticktick_cli", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self):
        self.calls = []
        self.task = {
            "id": "task-1",
            "projectId": "project-1",
            "title": "Old title",
            "content": "Old content",
            "priority": 0,
            "status": 2,
            "timeZone": "Europe/Prague",
            "isAllDay": False,
        }

    def list_projects(self):
        self.calls.append(("list_projects",))
        return [{"id": "project-1", "name": "Personal"}]

    def get_project_data(self, project_id):
        self.calls.append(("get_project_data", project_id))
        return {"tasks": [{"id": "task-1", "title": "Old title"}]}

    def create_task(self, payload):
        self.calls.append(("create_task", payload))
        return payload

    def move_task(self, from_project_id, to_project_id, task_id):
        self.calls.append(("move_task", from_project_id, to_project_id, task_id))
        return {"ok": True}

    def get_task(self, project_id, task_id):
        self.calls.append(("get_task", project_id, task_id))
        return dict(self.task)

    def update_task(self, task_id, payload):
        self.calls.append(("update_task", task_id, payload))
        self.task.update(payload)
        return dict(self.task)

    def complete_task(self, project_id, task_id):
        self.calls.append(("complete_task", project_id, task_id))
        return None

    def delete_task(self, project_id, task_id):
        self.calls.append(("delete_task", project_id, task_id))
        return None


class TickTickCliTests(unittest.TestCase):
    def test_parser_supports_expected_subcommands(self):
        cli = load_module()
        for argv in [
            ["projects"],
            ["tasks", "--project", "project-1"],
            ["create", "--title", "Hello"],
            ["move", "--task", "task-1", "--from-project", "inbox", "--to-project", "project-1"],
            ["update", "--task", "task-1", "--project", "project-1", "--title", "New"],
            ["done", "--task", "task-1", "--project", "project-1"],
            ["reopen", "--task", "task-1", "--project", "project-1"],
            ["delete", "--task", "task-1", "--project", "project-1"],
        ]:
            self.assertTrue(cli.parse_args(argv).command)

    def test_load_api_token_reads_env_file(self):
        cli = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "ticktick.env"
            env_path.write_text("TICKTICK_API_TOKEN=secret-token\n", encoding="utf-8")
            self.assertEqual(cli.load_api_token(env_path), "secret-token")

    def test_create_omits_project_for_inbox(self):
        cli = load_module()
        client = FakeClient()
        args = cli.parse_args(["create", "--title", "Inbox task", "--content", "Note"])
        cli.run_command(args, client, io.StringIO(), json_output=False)
        self.assertEqual(client.calls[0], ("create_task", {"title": "Inbox task", "content": "Note"}))

    def test_reopen_fetches_task_and_sets_status_zero(self):
        cli = load_module()
        client = FakeClient()
        args = cli.parse_args(["reopen", "--task", "task-1", "--project", "project-1"])
        cli.run_command(args, client, io.StringIO(), json_output=False)
        self.assertEqual(client.calls[0], ("get_task", "project-1", "task-1"))
        method, task_id, payload = client.calls[1]
        self.assertEqual((method, task_id), ("update_task", "task-1"))
        self.assertEqual(payload["status"], 0)

    def test_delete_dispatches_project_and_task_id(self):
        cli = load_module()
        client = FakeClient()
        args = cli.parse_args(["delete", "--task", "task-1", "--project", "project-1"])
        cli.run_command(args, client, io.StringIO(), json_output=False)
        self.assertEqual(client.calls[0], ("delete_task", "project-1", "task-1"))


if __name__ == "__main__":
    unittest.main()
