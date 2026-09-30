import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.runtime import RUNTIMES, Outcome
from server.store import Store

REPORT = "```markdown\n## 今日工作总结\n- 简历改完了\n\n## 明日工作计划\n- 复习数仓\n```"


class FakeRuntime:
    id, label, remote = "fake", "Fake", False

    def __init__(self, result=REPORT, during=None):
        self.result, self.during, self.prompts = result, during, []

    def command_path(self, settings):
        return "/bin/fake"

    def run(self, executable, prompt, workspace, on_start, on_log, settings):
        self.prompts.append(prompt)
        if self.during:
            self.during()
        return Outcome(True, result=self.result)


class DailyReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def todo(self, title, today=False, priority="medium"):
        return self.store.action("create_todo", {"title": title, "today": today, "priority": priority})

    def test_draft_has_summary_and_plan_sections(self):
        done = self.todo("改简历", today=True)
        self.todo("复习数仓", today=True, priority="high")
        self.todo("投递字节", priority="high")
        self.todo("整理书签")
        self.store.action("toggle_todo", {"id": done["id"]})
        summary, _, plan = self.store.action("draft_log", {})["summary"].partition("## 明日工作计划")
        self.assertIn("## 今日工作总结", summary)
        self.assertIn("改简历", summary)
        self.assertIn("[高] 复习数仓", plan)
        self.assertIn("[高] 投递字节", plan)
        self.assertNotIn("整理书签", plan)

    def test_engine_writes_report_when_no_draft_exists(self):
        self.todo("复习数仓", today=True, priority="high")
        self.store.action("create_rule", {"text": "日报不超过十行", "category": "Daily Log"})
        runtime = FakeRuntime()
        with patch.dict(RUNTIMES, {"kimi": runtime}):
            log = self.store.action("summarize_log", {"engine": "kimi"})
        self.assertEqual(log["summary"], "## 今日工作总结\n- 简历改完了\n\n## 明日工作计划\n- 复习数仓")
        self.assertEqual(log["revisions"], [])
        self.assertFalse(log["stale"])
        self.assertIn("Fake", log["message"])
        self.assertIn("复习数仓", runtime.prompts[0])
        self.assertIn("日报不超过十行", runtime.prompts[0])
        self.assertEqual(self.store.get("settings", "settings")["report_engine"], "kimi")

    def test_regenerating_keeps_previous_text_as_revision(self):
        self.todo("复习数仓", today=True)
        draft = self.store.action("draft_log", {})
        runtime = FakeRuntime()
        with patch.dict(RUNTIMES, {"kimi": runtime}):
            log = self.store.action("summarize_log", {"id": draft["id"], "engine": "kimi"})
        self.assertEqual(log["id"], draft["id"])
        self.assertEqual(log["revisions"][-1]["summary"], draft["summary"])
        self.assertIn(draft["summary"], runtime.prompts[0])

    def test_confirmed_log_and_unknown_engine_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "通道"):
            self.store.action("summarize_log", {"engine": "nope"})
        log = self.store.action("draft_log", {})
        self.store.action("confirm_log", {"id": log["id"]})
        with patch.dict(RUNTIMES, {"kimi": FakeRuntime()}), self.assertRaisesRegex(ValueError, "封存"):
            self.store.action("summarize_log", {"engine": "kimi"})

    def test_edit_during_generation_is_not_overwritten(self):
        log = self.store.action("draft_log", {})
        edit = lambda: self.store.action("update_log", {"id": log["id"], "summary": "我自己改的"})
        with patch.dict(RUNTIMES, {"kimi": FakeRuntime(during=edit)}), self.assertRaisesRegex(ValueError, "生成期间"):
            self.store.action("summarize_log", {"id": log["id"], "engine": "kimi"})
        self.assertEqual(self.store.get("daily_log", log["id"])["summary"], "我自己改的")


if __name__ == "__main__":
    unittest.main()
