from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_daily_loop_persists_and_generates_from_events(self):
        project = self.store.action("create_project", {"name": "测试项目"})
        task = self.store.action("create_task", {"title": "完成方案", "project_id": project["id"]})
        day = self.store.state()["today"]
        self.assertEqual(self.store.brief()[0]["task_id"], task["id"])
        plan = self.store.action("confirm_plan", {"task_ids": [task["id"]]})
        self.assertEqual(plan["date"], day)
        self.assertEqual(self.store.get("task", task["id"])["status"], "Planned")
        self.store.action("complete_task", {"id": task["id"]})
        log = self.store.action("draft_log", {})
        self.assertIn("完成方案", log["summary"])
        self.assertEqual(self.store.action("confirm_log", {"id": log["id"]})["confirmed_at"][:10], day)
        self.assertEqual([e["type"] for e in self.store.events(day)][:2], ["DailyLogConfirmed", "DailyLogDrafted"])
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get("task", task["id"])["status"], "Done")
        self.assertTrue(self.store.get("daily_log", log["id"])["confirmed_at"])

    def test_agent_task_cannot_be_marked_done_directly(self):
        task = self.store.action("create_task", {"title": "交给 Agent"})
        self.store.action("update_task", {"id": task["id"], "executor_type": "agent"})
        with self.assertRaisesRegex(ValueError, "必须经过审核"):
            self.store.action("complete_task", {"id": task["id"]})

    def test_plan_rejects_invalid_tasks_without_partial_changes(self):
        task = self.store.action("create_task", {"title": "有效任务"})
        with self.assertRaisesRegex(ValueError, "不存在"):
            self.store.action("confirm_plan", {"task_ids": [task["id"], "missing"]})
        self.assertEqual(self.store.get("task", task["id"])["status"], "Inbox")

    def test_knowledge_requires_approval_and_does_not_overwrite(self):
        vault = Path(self.temp.name) / "vault"
        vault.mkdir()
        task = self.store.action("create_task", {"title": "调研"})
        proposal = self.store.action("propose_knowledge", {"task_id": task["id"], "title": "调研结果", "content": "正文"})
        self.assertEqual(list(vault.rglob("*.md")), [])
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        written = self.store.action("approve_knowledge", {"id": proposal["id"], "choice": "write"})
        self.assertEqual(Path(written["path"]).read_text(), "# 调研结果\n\n正文\n")
        other = self.store.action("propose_knowledge", {"task_id": task["id"], "title": "调研结果", "content": "不同内容"})
        with self.assertRaisesRegex(ValueError, "已存在"):
            self.store.action("approve_knowledge", {"id": other["id"], "choice": "write"})
        self.assertEqual(Path(written["path"]).read_text(), "# 调研结果\n\n正文\n")

    def test_knowledge_rejects_symlink_outside_vault(self):
        vault = Path(self.temp.name) / "vault"
        outside = Path(self.temp.name) / "outside"
        vault.mkdir()
        outside.mkdir()
        (vault / "Personal-OS").symlink_to(outside, target_is_directory=True)
        task = self.store.action("create_task", {"title": "调研"})
        proposal = self.store.action("propose_knowledge", {"task_id": task["id"], "title": "不应外写", "content": "正文"})
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        with self.assertRaisesRegex(ValueError, "必须位于"):
            self.store.action("approve_knowledge", {"id": proposal["id"], "choice": "write"})
        self.assertEqual(list(outside.iterdir()), [])

    def test_agent_result_waits_for_user_review(self):
        workspace = Path(self.temp.name) / "workspace"
        workspace.mkdir()
        project = self.store.action("create_project", {"name": "项目"})
        self.store.action("update_project", {"id": project["id"], "workspace_path": str(workspace)})
        task = self.store.action("create_task", {"title": "实现功能", "project_id": project["id"], "executor_type": "agent"})

        class FakeProcess:
            returncode = 0
            def __init__(self, command, **kwargs):
                self.output = Path(command[command.index("-o") + 1])
                self.workspace = Path(command[command.index("-C") + 1])
            def communicate(self, prompt, timeout):
                (self.workspace / "hello.txt").write_text("验收产物", encoding="utf-8")
                self.output.write_text("已完成实现与验证", encoding="utf-8")
                return "", ""

        with patch("server.store.shutil.which", return_value="/fake/codex"), patch("server.store.subprocess.Popen", FakeProcess):
            self.store.action("start_agent", {"task_id": task["id"]})
            for _ in range(100):
                if self.store.get("task", task["id"])["status"] == "Review":
                    break
                time.sleep(0.01)
        self.assertEqual(self.store.get("task", task["id"])["status"], "Review")
        self.assertEqual(self.store.all("agent_run")[0]["status"], "Finished")
        artifact = self.store.all("artifact")[0]
        self.assertEqual((artifact["name"], artifact["change"], artifact["status"]), ("hello.txt", "Created", "Review"))
        with self.assertRaisesRegex(ValueError, "必须经过审核"):
            self.store.action("complete_task", {"id": task["id"]})
        self.store.action("review_agent", {"task_id": task["id"], "choice": "approve"})
        self.assertEqual(self.store.get("task", task["id"])["status"], "Done")
        self.assertEqual(self.store.get("artifact", artifact["id"])["status"], "Approved")

    def test_closing_client_interrupts_running_agent_and_blocks_task(self):
        workspace = Path(self.temp.name) / "workspace"
        workspace.mkdir()
        project = self.store.action("create_project", {"name": "项目"})
        self.store.action("update_project", {"id": project["id"], "workspace_path": str(workspace)})
        task = self.store.action("create_task", {"title": "执行中任务", "project_id": project["id"], "executor_type": "agent"})
        started = threading.Event()
        stopped = threading.Event()

        class WaitingProcess:
            returncode = None

            def __init__(self, _command, **_kwargs):
                started.set()

            def communicate(self, _prompt, timeout):
                if not stopped.wait(timeout):
                    raise AssertionError("未收到关闭信号")
                self.returncode = -15
                return "", ""

            def poll(self):
                return self.returncode

            def terminate(self):
                stopped.set()

            def kill(self):
                stopped.set()

        with patch("server.store.shutil.which", return_value="/fake/codex"), patch("server.store.subprocess.Popen", WaitingProcess):
            self.store.action("start_agent", {"task_id": task["id"]})
            self.assertTrue(started.wait(2))
            self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get("task", task["id"])["status"], "Blocked")
        self.assertEqual(self.store.all("agent_run")[0]["status"], "Interrupted")

    def test_obsidian_changes_are_evidence_not_automatic_completion(self):
        vault = Path(self.temp.name) / "vault"
        vault.mkdir()
        note = vault / "今天的笔记.md"
        note.write_text("研究内容", encoding="utf-8")
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        first = self.store.action("scan_obsidian", {})
        second = self.store.action("scan_obsidian", {})
        self.assertEqual(first["changes"], 1)
        self.assertEqual(second["changes"], 0)
        log = self.store.action("draft_log", {})
        self.assertIn("仅供核对，不自动计为完成", log["summary"])
        self.assertIn("今天的笔记.md", log["summary"])

    def test_generated_brief_uses_existing_task_and_active_decision(self):
        project = self.store.action("create_project", {"name": "项目"})
        task = self.store.action("create_task", {"title": "完成页面", "project_id": project["id"]})
        self.store.action("create_decision", {"title": "优先每日闭环", "project_id": project["id"]})
        output = '{"priorities":[{"task_id":"' + task["id"] + '","reason":"符合当前项目决策"}]}'
        with patch.object(self.store, "_codex_readonly", return_value=output) as model:
            brief = self.store.action("generate_brief", {})
        self.assertEqual(brief["priorities"][0]["task_id"], task["id"])
        self.assertIn("优先每日闭环", model.call_args.args[0])

    def test_channel_refresh_filters_and_deduplicates(self):
        channel = self.store.action("create_channel", {"name": "Agent", "boundary": "Agent", "filter_rule": "广告", "sources": "https://example.com/feed.xml", "daily_limit": 2})
        entries = [
            {"title": "Agent runtime", "summary": "研究进展", "url": "https://example.com/a", "published": ""},
            {"title": "Agent 广告", "summary": "营销", "url": "https://example.com/b", "published": ""},
            {"title": "其他新闻", "summary": "其他", "url": "https://example.com/c", "published": ""},
        ]
        with patch("server.store.fetch_feed", return_value=entries):
            first = self.store.action("refresh_channel", {"id": channel["id"]})
            second = self.store.action("refresh_channel", {"id": channel["id"]})
        self.assertEqual(first["added"], 1)
        self.assertEqual(second["added"], 0)
        self.assertIn("命中", self.store.all("intelligence_item")[0]["why_recommended"])


if __name__ == "__main__":
    unittest.main()
