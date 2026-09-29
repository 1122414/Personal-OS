from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from server.store import Store

KNOWLEDGE = """---
aliases:
  - 硬知识总览
tags:
  - 硬知识
status: active
---

# 硬知识学习路径

正文不应被改动。
"""


class ObsidianHomeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        (self.vault / "首页数据").mkdir(parents=True)
        (self.vault / "计算机").mkdir()
        (self.vault / "工作").mkdir()
        self.knowledge = self.vault / "计算机" / "学习路径.md"
        self.knowledge.write_text(KNOWLEDGE)
        self.recruiting = self.vault / "工作" / "秋招准备.md"
        self.recruiting.write_text("# 秋招准备\n\n## 记录\n")
        self.progress = self.vault / "工作" / "秋招学习进度.md"
        self.progress.write_text("---\nhome_progress: 复习简历拷打\nhome_status: paused\n---\n# 秋招学习进度\n")
        tasks = [{"id": "knowledge", "title": "硬知识系统学习", "note": "计算机/学习路径.md"},
                 {"id": "recruiting", "title": "秋招准备", "note": "工作/秋招准备.md"},
                 {"id": "study", "title": "秋招学习进度", "note": "工作/秋招学习进度.md"},
                 {"id": "missing", "title": "缺失", "note": "工作/不存在.md"},
                 {"id": "escape", "title": "越界", "note": "../outside.md"}]
        (self.vault / "首页数据" / "工作台.json").write_text(json.dumps({"version": 1, "tasks": tasks}, ensure_ascii=False))
        self.store = Store(self.root / "test.sqlite3")
        self.store.action("save_settings", {"obsidian_vault": str(self.vault)})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def items(self):
        return {item["id"]: item for item in self.store.state()["home_items"]["items"]}

    def update(self, item_id, field, value, version=None):
        item = self.items()[item_id]
        return self.store.action("update_home_item", {"note": item["note"], "field": field, "value": value, "expected_version": version or item["version"], "title": item["title"]})

    def test_next_step_becomes_todo_and_prompts_for_a_new_one_without_writing_obsidian(self):
        self.progress.write_text("---\nhome_next: 过一遍  项目难点\n---\n# 秋招学习进度\n")
        before = self.progress.read_text()
        item = self.items()["study"]
        self.assertIsNone(item["next_todo"])
        payload = {"title": item["home_next"], "today": True, "home_item_note": item["note"], "home_next_snapshot": item["home_next"]}
        todo = self.store.action("create_todo", payload)
        self.assertEqual(self.store.action("create_todo", payload)["id"], todo["id"])
        self.assertEqual(self.items()["study"]["next_todo"], {"id": todo["id"], "done": False, "planned_date": todo["planned_date"]})
        self.store.action("toggle_todo", {"id": todo["id"]})
        self.assertTrue(self.items()["study"]["next_todo"]["done"])
        self.assertEqual(self.progress.read_text(), before)
        self.update("study", "home_next", "模拟面试一次")
        self.assertIsNone(self.items()["study"]["next_todo"])
        self.assertEqual(len(self.store.all("todo")), 1)

    def test_reads_progress_status_and_reports_broken_links(self):
        items = self.items()
        self.assertEqual((items["study"]["home_progress"], items["study"]["home_status"]), ("复习简历拷打", "paused"))
        self.assertEqual((items["knowledge"]["home_progress"], items["knowledge"]["home_status"]), ("", "active"))
        self.assertIn("不存在", items["missing"]["error"])
        self.assertIn("vault 内", items["escape"]["error"])
        self.assertIsNone(items["escape"]["version"])

    def test_H05_update_changes_only_the_target_field(self):
        self.update("knowledge", "home_next", "补完 React 渲染: 调和阶段")
        text = self.knowledge.read_text()
        self.assertEqual(text, KNOWLEDGE.replace("status: active\n", 'status: active\nhome_next: "补完 React 渲染: 调和阶段"\n'))
        self.assertEqual(self.items()["knowledge"]["home_next"], "补完 React 渲染: 调和阶段")
        self.update("study", "home_progress", "项目深挖")
        self.assertEqual(self.progress.read_text(), '---\nhome_progress: "项目深挖"\nhome_status: paused\n---\n# 秋招学习进度\n')
        self.assertEqual(self.store.events()[0]["type"], "HomeItemUpdated")

    def test_note_without_frontmatter_gets_one_and_keeps_body(self):
        self.update("recruiting", "home_status", "done")
        self.assertEqual(self.recruiting.read_text(), '---\nhome_status: "done"\n---\n# 秋招准备\n\n## 记录\n')
        self.assertEqual(self.items()["recruiting"]["home_status"], "done")

    def test_H06_changed_note_is_not_overwritten(self):
        stale = self.items()["study"]["version"]
        self.progress.write_text(self.progress.read_text() + "\nObsidian 里的新内容\n")
        os.utime(self.progress, ns=(1, 1))
        with self.assertRaisesRegex(ValueError, "别处修改"):
            self.update("study", "home_next", "覆盖", version=stale)
        self.assertIn("Obsidian 里的新内容", self.progress.read_text())
        self.assertNotIn("覆盖", self.progress.read_text())

    def test_rejects_unknown_fields_bad_status_and_paths_outside_vault(self):
        with self.assertRaisesRegex(ValueError, "只能修改"):
            self.update("study", "status", "x")
        with self.assertRaisesRegex(ValueError, "状态无效"):
            self.update("study", "home_status", "later")
        with self.assertRaisesRegex(ValueError, "vault 内"):
            self.store.action("update_home_item", {"note": "../outside.md", "field": "home_next", "value": "x", "expected_version": "0:0"})

    def test_H07_missing_vault_or_config_is_quiet(self):
        (self.vault / "首页数据" / "工作台.json").unlink()
        home = self.store.state()["home_items"]
        self.assertEqual((home["configured"], home["items"]), (False, []))
        self.store.action("save_settings", {"obsidian_vault": ""})
        home = self.store.state()["home_items"]
        self.assertEqual((home["configured"], home["items"]), (False, []))
        self.assertTrue(home["errors"])


if __name__ == "__main__":
    unittest.main()
