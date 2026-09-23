from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
