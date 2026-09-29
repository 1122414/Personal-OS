"""Multica runtime tests.

The CLI responses here are hand-written from `multica issue ... --help` (CLI 0.4.14);
they have not been checked against a real Multica server.
"""

from __future__ import annotations

import json
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.runtime import RUNTIMES
from server.store import Store


class FakeMultica:
    """Scripted `multica` CLI: records calls and answers `issue` subcommands."""

    def __init__(self, statuses, messages=None, error=""):
        self.calls, self.stdin = [], []
        self.statuses, self.messages, self.error = list(statuses), messages or {}, error
        self.tasks = [{"id": "task-1", "created_at": "2026-09-29T08:00:00Z"}]
        self.lock = threading.Lock()

    def __call__(self, command, input=None, **kwargs):
        with self.lock:
            args = command[1:command.index("--output")]
            if args[:2] == ["--profile", "work"]:
                args = args[2:]
            self.calls.append(args)
            if input is not None:
                self.stdin.append(input)
            action = args[1]
            if action == "create":
                body = {"id": "issue-1", "identifier": "PER-1", "title": args[args.index("--title") + 1]}
            elif action == "runs":
                status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
                body = [{**task, "status": status, "error": self.error} for task in self.tasks]
                body[-1]["status"] = status
                for task in body[:-1]:
                    task["status"] = "completed"
            elif action == "run-messages":
                since = int(args[args.index("--since") + 1])
                body = [item for item in self.messages.get(args[2], []) if item["seq"] > since]
            elif action == "rerun":
                self.tasks.append({"id": "task-2", "created_at": "2026-09-29T09:00:00Z"})
                body = {"id": "issue-1"}
            else:
                body = {"ok": True}
            return subprocess.CompletedProcess(command, 0, json.dumps(body), "")

    def actions(self):
        return [call[1] for call in self.calls]


MESSAGES = {"task-1": [{"seq": 1, "type": "text", "content": "读取仓库"},
                       {"seq": 2, "type": "tool_use", "tool": "Write", "input": {"path": "notes.md"}},
                       {"seq": 3, "type": "text", "content": "已完成并通过测试"}],
            "task-2": [{"seq": 1, "type": "text", "content": "第二次完成"}]}


class MulticaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.cli = self.root / "multica"
        self.cli.write_text("#!/bin/sh\n")
        self.cli.chmod(self.cli.stat().st_mode | stat.S_IXUSR)
        self.store = Store(self.root / "test.sqlite3")
        project = self.store.action("create_project", {"name": "项目", "workspace_path": str(self.workspace)})
        self.task = self.store.action("create_task", {"title": "整理笔记", "project_id": project["id"], "executor_type": "agent", "runtime": "multica"})
        patcher = patch.object(RUNTIMES["multica"], "poll_seconds", 0.01)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def configure(self):
        self.store.action("save_settings", {"multica_command": str(self.cli), "multica_profile": "work", "multica_agent": "coder"})

    def fake(self, cli):
        patcher = patch("server.runtime.subprocess.run", cli)
        patcher.start()
        self.addCleanup(patcher.stop)
        return cli

    def wait_run(self, run_id, statuses=("Finished", "Failed", "Canceled")):
        for _ in range(500):
            run = self.store.get("agent_run", run_id)
            if run["status"] in statuses and run_id not in self.store._workers:
                return run
            time.sleep(0.01)
        self.fail(f"执行未结束：{self.store.get('agent_run', run_id)['status']}")

    def test_disabled_until_command_and_agent_are_set(self):
        with patch("server.runtime.shutil.which", return_value="/opt/homebrew/bin/multica"):
            multica = next(a for a in self.store.state()["runtime"]["agents"] if a["id"] == "multica")
            self.assertEqual((multica["available"], multica["remote"]), (False, True))
            with self.assertRaisesRegex(ValueError, "本机未找到 Multica 命令行"):
                self.store.action("start_agent", {"task_id": self.task["id"]})
        with self.assertRaisesRegex(ValueError, "配置档名称"):
            self.store.action("save_settings", {"multica_profile": "work; rm"})

    def test_dispatch_creates_assigned_issue_and_follows_run_to_review(self):
        self.configure()
        cli = self.fake(FakeMultica(["queued", "running", "completed"], MESSAGES))
        run = self.wait_run(self.store.action("start_agent", {"task_id": self.task["id"]})["id"])
        self.assertEqual((run["status"], run["runtime"], run["external_id"]), ("Finished", "multica", "issue-1"))
        self.assertEqual(run["result"], "已完成并通过测试")
        self.assertEqual(run["log_tail"], ["已创建 Multica issue PER-1，指派给 coder", "读取仓库", "Write notes.md", "已完成并通过测试"])
        create = cli.calls[0]
        self.assertEqual(create[:2], ["issue", "create"])
        self.assertEqual(create[create.index("--title") + 1], "整理笔记")
        self.assertEqual(create[create.index("--assignee") + 1], "coder")
        self.assertIn(f"Personal OS 本地工作目录：{self.workspace.resolve()}", cli.stdin[0])
        self.assertEqual(self.store.get("task", self.task["id"])["status"], "Review")

    def test_failed_remote_run_blocks_task_with_its_error(self):
        self.configure()
        self.fake(FakeMultica(["running", "failed"], MESSAGES, error="agent 退出码 1"))
        run = self.wait_run(self.store.action("start_agent", {"task_id": self.task["id"]})["id"])
        self.assertEqual((run["status"], run["error"]), ("Failed", "agent 退出码 1"))
        self.assertEqual(self.store.get("task", self.task["id"])["status"], "Blocked")

    def test_cancel_asks_multica_to_cancel_the_task(self):
        self.configure()
        cli = self.fake(FakeMultica(["running"]))
        run = self.store.action("start_agent", {"task_id": self.task["id"]})
        for _ in range(200):
            if "runs" in cli.actions():
                break
            time.sleep(0.01)
        self.store.action("cancel_agent", {"id": run["id"]})
        self.wait_run(run["id"], ("Canceled",))
        for _ in range(200):
            if "cancel-task" in cli.actions():
                break
            time.sleep(0.01)
        self.assertIn(["issue", "cancel-task", "task-1", "--issue", "issue-1"], cli.calls)

    def test_restart_resumes_following_instead_of_interrupting(self):
        self.configure()
        cli = self.fake(FakeMultica(["running"], MESSAGES))
        run = self.store.action("start_agent", {"task_id": self.task["id"]})
        for _ in range(200):
            if self.store.get("agent_run", run["id"])["external_id"]:
                break
            time.sleep(0.01)
        self.store.close()
        cli.statuses = ["completed"]
        self.store = Store(self.root / "test.sqlite3")
        resumed = self.wait_run(run["id"])
        self.assertEqual((resumed["status"], resumed["external_id"], resumed["error"]), ("Finished", "issue-1", ""))
        self.assertEqual(cli.actions().count("create"), 1)
        self.assertNotIn("cancel-task", cli.actions())
        self.assertNotIn("AgentRunInterrupted", [event["type"] for event in self.store.state()["events"]])

    def test_rerun_after_review_reuses_the_issue(self):
        self.configure()
        cli = self.fake(FakeMultica(["completed"], MESSAGES))
        self.wait_run(self.store.action("start_agent", {"task_id": self.task["id"]})["id"])
        rerun = self.wait_run(self.store.action("review_agent", {"task_id": self.task["id"], "choice": "rerun"})["id"])
        self.assertEqual(cli.actions().count("create"), 1)
        self.assertIn(["issue", "rerun", "issue-1"], cli.calls)
        self.assertEqual((rerun["status"], rerun["external_id"], rerun["result"]), ("Finished", "issue-1", "第二次完成"))


if __name__ == "__main__":
    unittest.main()
