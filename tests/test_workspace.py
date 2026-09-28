from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.store import Store


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "workspace.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def record(self, content="想到用装饰器为脚本计时", **extra):
        return self.store.action("create_record", {"content": content, **extra})

    def test_A01_capture_preserves_original_whitespace_without_agent_or_task(self):
        content = "\n今天的原话\n    indented_code()\n"
        with patch("server.store.subprocess.Popen") as agent:
            record = self.record(content)
            agent.assert_not_called()
        self.assertEqual(self.store.all("task"), [])
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.get("record", record["id"])["content"], content)
        self.assertEqual(self.store.get("record", record["id"])["created_at"], record["created_at"])

    def test_A02_topics_keep_stable_record_links_and_edit_conflicts(self):
        record = self.record()
        topic = self.store.action("create_learning_topic", {"record_id": record["id"]})
        self.assertEqual(topic["record_ids"], [record["id"]])
        self.assertIsNone(topic["native_session_id"])
        edited = self.store.action("update_record", {"id": record["id"], "expected_updated_at": record["updated_at"], "content": "新的补充"})
        self.assertEqual(edited["original_content"], record["content"])
        with self.assertRaisesRegex(ValueError, "别处修改"):
            self.store.action("update_record", {"id": record["id"], "expected_updated_at": record["updated_at"], "content": "过期页面"})
        self.assertEqual(self.store.get("learning_topic", topic["id"])["record_ids"], [record["id"]])
        for _ in range(2):
            self.store.action("link_record", {"id": topic["id"], "record_id": record["id"]})
        self.assertEqual(len(self.store.get("learning_topic", topic["id"])["record_ids"]), 1)

    def test_A09_save_is_distinct_from_parse_and_use_and_original_is_in_backup(self):
        record = self.record()
        body = b"%PDF-1.4\noriginal data"
        material = self.store.action("add_material", {"record_id": record["id"], "name": "../../original.pdf", "base64": base64.b64encode(body).decode()})
        self.assertEqual(material["read_status"], "saved")
        self.assertEqual(material["used_in"], [])
        self.assertNotIn("body", self.store.state()["materials"][0])
        backup = self.store.action("create_backup", {})
        self.store.db.execute("DELETE FROM material_blobs")
        self.store.db.commit()
        self.store.action("restore_backup", backup)
        self.assertEqual(self.store.material_original(material["id"])[1], body)
        exported = self.store.action("export_data", {})
        self.assertEqual(base64.b64decode(json.loads(Path(exported["path"]).read_text())["attachments"][0]["base64"]), body)

    def test_A09_reject_active_files_invalid_urls_and_attachment_data(self):
        record = self.record()
        for payload in ({"name": "bad.svg", "base64": base64.b64encode(b"<svg onload='bad'/>").decode()},
                        {"name": "bad.png", "base64": "@@@"}, {"url": "javascript:alert(1)"},
                        {"url": "https://user:secret@example.com"}, {"url": "file:///etc/passwd"}):
            with self.assertRaises(ValueError):
                self.store.action("add_material", {"record_id": record["id"], **payload})
        self.assertEqual(self.store.all("material"), [])
        with patch("server.workspace.MAX_ATTACHMENT_BYTES", 2):
            with self.assertRaisesRegex(ValueError, "20 MB"):
                self.store.action("add_material", {"record_id": record["id"], "name": "too-big.pdf", "base64": "JVBERi0="})
        link = self.store.action("add_material", {"record_id": record["id"], "url": "https://example.com/article"})
        self.assertEqual(link["read_status"], "saved")

    def test_A12_only_explicit_conversion_creates_task_and_is_idempotent(self):
        record = self.record()
        self.assertFalse(self.store.all("task"))
        task = self.store.action("record_to_task", {"id": record["id"]})
        again = self.store.action("record_to_task", {"id": record["id"]})
        self.assertEqual(task["id"], again["id"])
        self.assertEqual(task["record_id"], record["id"])
        self.assertEqual(task["status"], "Inbox")
        self.assertEqual(task["executor_type"], "self")

    def test_A13_export_keeps_original_attachment_and_never_overwrites(self):
        vault = Path(self.temp.name) / "vault"
        vault.mkdir()
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        record = self.record("正文 **很重要**\n\n```python\nprint('ok')\n```", title="../学习笔记")
        body = b"%PDF-1.4\nhello"
        material = self.store.action("add_material", {"record_id": record["id"], "name": "reference.pdf", "base64": base64.b64encode(body).decode()})
        first = self.store.action("export_workspace_note", {"id": record["id"], "destination": "obsidian"})
        first_text = Path(first["path"]).read_text()
        self.assertIn(record["content"], first_text)
        self.assertTrue(Path(first["path"]).is_relative_to(vault.resolve()))
        self.assertEqual((Path(first["path"]).parent / f"{material['id']}.pdf").read_bytes(), body)
        self.store.action("update_record", {"id": record["id"], "expected_updated_at": record["updated_at"], "content": "新版"})
        second = self.store.action("export_workspace_note", {"id": record["id"], "destination": "obsidian"})
        self.assertNotEqual(first["path"], second["path"])
        self.assertEqual(Path(first["path"]).read_text(), first_text)

    def test_export_rejects_symlink_target(self):
        vault = Path(self.temp.name) / "vault"
        outside = Path(self.temp.name) / "outside"
        vault.mkdir(); outside.mkdir()
        (vault / "Personal-OS").symlink_to(outside, target_is_directory=True)
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        with self.assertRaisesRegex(ValueError, "符号链接"):
            self.store.action("export_workspace_note", {"id": self.record()["id"], "destination": "obsidian"})
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_topic_mode_and_record_type_are_rejected(self):
        with self.assertRaises(ValueError):
            self.record(record_type="task")
        with self.assertRaises(ValueError):
            self.store.action("create_learning_topic", {"title": "测试", "mode": "autonomous"})
        self.assertEqual(self.store.all("learning_topic"), [])

    def test_restore_pre_attachment_database_recreates_blob_table(self):
        self.store.db.execute("DROP TABLE material_blobs")
        self.store.db.commit()
        backup = self.store.action("create_backup", {})
        self.store.init_workspace()
        self.store.action("restore_backup", backup)
        self.assertEqual(self.store.export_blobs(), [])

    def test_obsidian_import_is_selected_snapshot_and_rejects_escape(self):
        vault = Path(self.temp.name) / "vault"
        vault.mkdir()
        note = vault / "笔记.md"
        note.write_text("原文", encoding="utf-8")
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        topic = self.store.action("create_learning_topic", {"title": "学习"})
        record = self.store.action("import_obsidian_record", {"id": topic["id"], "path": "笔记.md"})
        self.assertEqual(record["content"], "原文")
        self.store.action("update_record", {"id": record["id"], "expected_updated_at": record["updated_at"], "content": "本地编辑"})
        self.assertEqual(note.read_text(), "原文")
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("not imported")
        (vault / "escape.md").symlink_to(outside)
        for relative in ("../outside.md", str(outside), "escape.md"):
            with self.assertRaises(ValueError):
                self.store.action("import_obsidian_record", {"id": topic["id"], "path": relative})


if __name__ == "__main__":
    unittest.main()
