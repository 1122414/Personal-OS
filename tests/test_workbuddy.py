import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from server.store import Store, local_day
from server.workbuddy import read_updates


class WorkBuddyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "workbuddy"
        self.source.mkdir()
        self.db = self.source / "workbuddy.db"
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE sessions(id TEXT, title TEXT, custom_title TEXT, status TEXT, cwd TEXT, created_at INTEGER, updated_at INTEGER, deleted_at INTEGER)")
            now = int(datetime.now().timestamp() * 1000)
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)", ("session-one", "研究报告", "", "completed", "/fixture", now, now, None))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)", ("deleted", "已删除", "", "completed", "/fixture", now, now, now))
        folder = self.source / "projects" / "fixture"
        folder.mkdir(parents=True)
        self.transcript = folder / "session-one.jsonl"
        messages = [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "研究目标"}], "providerData": {"credential": "NEVER_COPY"}},
            {"type": "reasoning", "rawContent": [{"type": "text", "text": "PRIVATE_REASONING"}]},
            {"type": "function_call_result", "output": {"text": "TOOL_SECRET"}},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "有来源的研究结果"}]},
        ]
        self.transcript.write_text("\n".join(json.dumps(x) for x in messages) + "\n")
        self.since = (datetime.now() - timedelta(days=7)).date().isoformat()
        self.store = Store(self.root / "personal-os.sqlite3")
        self.store.action("save_settings", {"workbuddy_root": str(self.source), "workbuddy_since": self.since, "workbuddy_enabled": True})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_read_only_visible_messages_and_idempotent_sync(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        first = self.store.action("sync_workbuddy", {})
        self.assertEqual(first["added"], 1)
        item = self.store.all("intelligence_item")[0]
        self.assertIn("研究结果", item["content"])
        for secret in ("NEVER_COPY", "PRIVATE_REASONING", "TOOL_SECRET"):
            self.assertNotIn(secret, item["content"])
        second = self.store.action("sync_workbuddy", {})
        self.assertEqual((second["added"], second["updated"], second["unchanged"]), (0, 0, 1))
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        self.assertEqual(self.store.all("task"), [])
        log = self.store.action("draft_log", {})
        self.assertIn("不计为任务完成", log["summary"])

    def test_source_updates_preserve_feedback_and_knowledge_requires_review(self):
        self.store.action("sync_workbuddy", {})
        item = self.store.all("intelligence_item")[0]
        self.store.action("feedback_intelligence", {"id": item["id"], "feedback": "ignore"})
        with self.transcript.open("a") as stream:
            stream.write(json.dumps({"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "updated answer"}]}) + "\n")
        result = self.store.action("sync_workbuddy", {})
        self.assertEqual(result["updated"], 1)
        updated = self.store.get("intelligence_item", item["id"])
        self.assertEqual(updated["feedback"], "ignore")
        self.assertEqual(updated["summary"], "updated answer")
        proposal = self.store.action("propose_intelligence_knowledge", {"id": item["id"]})
        again = self.store.action("propose_intelligence_knowledge", {"id": item["id"]})
        self.assertEqual(proposal["id"], again["id"])
        self.assertEqual(proposal["status"], "Review")
        vault = self.root / "vault"
        vault.mkdir()
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        self.assertEqual(list(vault.iterdir()), [])
        result = self.store.action("approve_knowledge", {"id": proposal["id"], "choice": "write"})
        self.assertTrue(Path(result["path"]).is_file())

    def test_missing_or_unrecognized_source_does_not_erase_previous_import(self):
        self.store.action("sync_workbuddy", {})
        self.transcript.unlink()
        result = self.store.action("sync_workbuddy", {})
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(len(self.store.all("intelligence_item")), 1)
        with sqlite3.connect(self.db) as db:
            db.execute("DROP TABLE sessions")
        with self.assertRaisesRegex(ValueError, "格式已变化"):
            self.store.action("sync_workbuddy", {})
        self.assertEqual(len(self.store.all("intelligence_item")), 1)

    def test_symlink_and_corrupt_lines_are_not_silently_trusted(self):
        with self.transcript.open("a") as stream:
            stream.write('{"partial":')
        result = read_updates(str(self.source), self.since, {})
        self.assertTrue(result["records"][0]["content_incomplete"])
        target = self.root / "outside.jsonl"
        self.transcript.rename(target)
        self.transcript.symlink_to(target)
        result = read_updates(str(self.source), self.since, {})
        self.assertEqual(result["records"], [])
        self.assertEqual(len(result["errors"]), 1)
        projects = self.source / "projects"
        outside = self.root / "outside-projects"
        projects.rename(outside)
        projects.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "正文目录"):
            read_updates(str(self.source), self.since, {})

    def test_feedback_changed_while_reading_is_preserved(self):
        self.store.action("sync_workbuddy", {})
        item = self.store.all("intelligence_item")[0]
        with self.transcript.open("a") as stream:
            stream.write(json.dumps({"type": "message", "role": "assistant", "content": [{"type": "text", "text": "changed"}]}) + "\n")

        def reading(*args):
            result = read_updates(*args)
            self.store.action("feedback_intelligence", {"id": item["id"], "feedback": "ignore"})
            return result

        with patch("server.store.read_updates", side_effect=reading):
            self.store.action("sync_workbuddy", {})
        self.assertEqual(self.store.get("intelligence_item", item["id"])["feedback"], "ignore")

    def test_newest_source_precedes_later_imported_older_records(self):
        newest = self.store.put("intelligence_item", {"title": "new", "source_updated_at": "2026-09-28T15:00:00+08:00"})
        oldest = self.store.put("intelligence_item", {"title": "old", "source_updated_at": "2026-09-22T15:00:00+08:00"})
        self.assertEqual([item["id"] for item in self.store.state()["intelligence_items"]], [newest["id"], oldest["id"]])

    def test_research_task_carries_source_and_waits_for_user_to_start(self):
        self.store.action("sync_workbuddy", {})
        item = self.store.all("intelligence_item")[0]
        self.store.put("intelligence_item", {**item, "title": "长" * 300})
        task = self.store.action("research_intelligence", {"id": item["id"]})
        self.assertEqual(task["intelligence_id"], item["id"])
        self.assertIn(str(self.transcript), task["description"])
        self.assertIn("有来源的研究结果", task["description"])
        self.assertEqual(task["status"], "Inbox")
        self.assertEqual(len(task["title"]), 200)
        self.assertEqual(self.store.all("agent_run"), [])
