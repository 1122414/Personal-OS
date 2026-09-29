from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from server.learning_summary import SECTION_TITLES
from server.store import Store, stamp


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "summary.sqlite3"
        self.store = Store(self.path)
        self.topic = self.store.action("create_learning_topic", {"title": "Python 装饰器", "goal": "理解参数透传"})
        self.question, self.answer = self.add_exchange("参数应该怎么传递？", "使用 *args 将位置参数原样传给函数。")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def add_exchange(self, question, answer):
        user = self.store.put("learning_message", {"topic_id": self.topic["id"], "role": "user", "content": question, "status": "Saved", "revision": 1, "sources": [], "important": False})
        assistant = self.store.put("learning_message", {"topic_id": self.topic["id"], "role": "assistant", "content": answer, "status": "Completed", "revision": 1, "sources": [], "important": False})
        topic = self.store.get("learning_topic", self.topic["id"])
        topic.update(last_completed_at=stamp(), last_activity_at=stamp(), summary_pending=True)
        self.store.put("learning_topic", topic)
        return user, assistant

    def output(self, text="- 包装器接收参数，再将它们传给原函数。\n  例如 `func(*args)` 保留位置参数。"):
        result = {key: {"body": "", "sources": []} for key in SECTION_TITLES}
        result["brief"] = {"body": "正在学习装饰器的参数透传，上次讨论了 *args，尚未独立练习。", "sources": ["message:" + self.answer["id"]]}
        result["goal"] = {"body": "理解参数透传", "sources": ["topic:" + self.topic["id"]]}
        result["understanding"] = {"body": text, "sources": ["message:" + self.answer["id"]]}
        result["questions"] = {"body": "如何处理关键字参数？", "sources": ["message:" + self.question["id"]]}
        result["next"] = {"body": "试着包装一个接收两个参数的函数。", "sources": [], "owner": "ai_suggestion"}
        return result

    def wait(self):
        deadline = time.monotonic() + 3
        while self.store._workers and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertFalse(self.store._workers)

    def generate(self, output=None):
        with patch.object(self.store, "_summary_output", return_value=output or self.output()):
            self.store.action("refresh_learning_summary", {"id": self.topic["id"]})
            self.wait()
        return self.store.summary_view(self.topic["id"])

    def test_A04_idle_two_minutes_and_no_duplicate_generation(self):
        last = datetime.fromisoformat(self.store.get("learning_topic", self.topic["id"])["last_activity_at"])
        with patch.object(self.store, "_summary_output", return_value=self.output()) as generate:
            self.store.summary_tick(last + timedelta(seconds=119))
            generate.assert_not_called()
            self.store.summary_tick(last + timedelta(seconds=121)); self.wait()
            self.store.summary_tick(last + timedelta(days=2)); self.wait()
            self.assertEqual(generate.call_count, 1)
        self.assertEqual(self.store.summary_view(self.topic["id"])["state"], "ready")

    def test_A04_new_messages_during_generation_keep_report_stale(self):
        started, release = threading.Event(), threading.Event()
        def generate(snapshot, cancel):
            started.set(); release.wait(2); return self.output()
        with patch.object(self.store, "_summary_output", side_effect=generate):
            self.store.action("refresh_learning_summary", {"id": self.topic["id"]})
            self.assertTrue(started.wait(1))
            self.add_exchange("还有 **kwargs 呢？", "传递关键字参数。")
            release.set(); self.wait()
        view = self.store.summary_view(self.topic["id"])
        self.assertEqual(view["state"], "stale")
        self.assertTrue(view["stale"])
        self.assertEqual(view["report"]["coverage"]["message_count"], 2)

    def test_A05_failure_keeps_old_report_and_does_not_auto_retry_forever(self):
        first = self.generate()["report"]
        self.add_exchange("换一个例子", "另一个例子")
        with patch.object(self.store, "_summary_output", side_effect=ValueError("模拟网络失败")) as generate:
            self.store.action("refresh_learning_summary", {"id": self.topic["id"]}); self.wait()
            self.store.summary_tick(datetime.now().astimezone() + timedelta(days=1)); self.wait()
            self.assertEqual(generate.call_count, 1)
        view = self.store.summary_view(self.topic["id"])
        self.assertEqual(view["state"], "failed")
        self.assertEqual(view["report"], first)

    def test_A05_interrupted_summary_resumes_after_restart(self):
        started = threading.Event()
        def generate(snapshot, cancel):
            started.set(); cancel.wait(2); raise ValueError("closing")
        with patch.object(self.store, "_summary_output", side_effect=generate):
            self.store.action("refresh_learning_summary", {"id": self.topic["id"]})
            self.assertTrue(started.wait(1))
            self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.summary_view(self.topic["id"])["state"], "pending")
        with patch.object(self.store, "_summary_output", return_value=self.output()):
            self.store.summary_tick(datetime.now().astimezone() + timedelta(minutes=3)); self.wait()
        self.assertEqual(self.store.summary_view(self.topic["id"])["state"], "ready")

    def test_A06_explanation_is_not_mastery_and_user_evidence_is_explicit(self):
        invalid = self.output("你已经掌握参数透传。")
        view = self.generate(invalid)
        self.assertEqual(view["state"], "failed")
        self.assertIn("缺少", view["error"])
        self.assertIn("尚无独立练习", view["evidence"])
        self.store.action("set_learning_evidence", {"id": self.question["id"], "signal": "understood"})
        self.assertIn("尚无已核对", self.store.summary_view(self.topic["id"])["evidence"])
        self.store.action("set_learning_evidence", {"id": self.question["id"], "signal": "exercise_verified"})
        self.assertIn("由你确认", self.store.summary_view(self.topic["id"])["evidence"])
        with self.assertRaises(ValueError):
            self.store.action("set_learning_evidence", {"id": self.answer["id"], "signal": "exercise_verified"})

    def test_A06_negated_mastery_is_not_mistaken_for_a_positive_claim(self):
        view = self.generate(self.output("本次只有讲解，不能据此判断你已经掌握。"))
        self.assertEqual(view["state"], "ready")
        self.assertIn("尚无独立练习", view["evidence"])

    def test_user_plan_can_reference_a_user_written_record(self):
        record = self.store.action("create_record", {"content": "我打算先练习参数透传。"})
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        output = self.output()
        output["next"] = {"body": "先练习参数透传。", "sources": [f"record:{record['id']}:1"], "owner": "user_plan"}
        self.assertEqual(self.generate(output)["state"], "ready")

    def test_A07_manual_sections_and_edits_during_generation_are_never_overwritten(self):
        report = self.generate()["report"]
        key = "understanding"
        first_edit = self.store.action("edit_summary_section", {"id": self.topic["id"], "key": key, "expected_revision": report["sections"][key]["revision"], "body": "我的纠正：保留对象而不是复制值。"})
        self.add_exchange("补一个新问题", "补一个回答")
        started, release = threading.Event(), threading.Event()
        def generate(snapshot, cancel):
            self.assertTrue(snapshot["base_sections"][key]["manual"])
            started.set(); release.wait(2); return self.output("候选：函数包装的新解释。")
        with patch.object(self.store, "_summary_output", side_effect=generate):
            self.store.action("refresh_learning_summary", {"id": self.topic["id"]})
            self.assertTrue(started.wait(1))
            second = self.store.action("edit_summary_section", {"id": self.topic["id"], "key": key, "expected_revision": first_edit["revision"], "body": "生成中又补充的人工说明。"})
            release.set(); self.wait()
        view = self.store.summary_view(self.topic["id"])
        self.assertEqual(view["report"]["sections"][key]["body"], second["body"])
        candidate = next(c for c in view["candidates"] if c["key"] == key)
        self.assertIn("新解释", candidate["generated"]["body"])
        self.assertTrue(view["versions"])
        with self.assertRaisesRegex(ValueError, "又有修改"):
            self.store.action("resolve_summary_candidate", {"id": candidate["id"], "choice": "accept", "expected_revision": first_edit["revision"]})
        self.store.action("resolve_summary_candidate", {"id": candidate["id"], "choice": "keep"})
        self.assertEqual(self.store.summary_view(self.topic["id"])["report"]["sections"][key]["body"], second["body"])

    def test_A07_first_generation_cannot_overwrite_a_new_manual_section(self):
        started, release = threading.Event(), threading.Event()
        def generate(snapshot, cancel): started.set(); release.wait(2); return self.output()
        with patch.object(self.store, "_summary_output", side_effect=generate):
            self.store.action("refresh_learning_summary", {"id": self.topic["id"]}); self.assertTrue(started.wait(1))
            self.store.action("edit_summary_section", {"id": self.topic["id"], "key": "goal", "expected_revision": 0, "body": "先理解函数调用"})
            release.set(); self.wait()
        self.assertEqual(self.store.summary_view(self.topic["id"])["report"]["sections"]["goal"]["body"], "先理解函数调用")

    def test_A08_sources_versions_restore_and_markdown_export(self):
        body = "- 参数按原顺序传递\n\n> 保留疑问\n\n```python\ndef wrapper(*args):\n    return func(*args)\n```\n<script>alert('x')</script>"
        first = self.generate(self.output(body))["report"]
        original = first["sections"]["understanding"]
        edit = self.store.action("edit_summary_section", {"id": self.topic["id"], "key": "understanding", "expected_revision": original["revision"], "body": "临时改写"})
        version = self.store.summary_view(self.topic["id"])["versions"][0]
        restored = self.store.action("restore_summary_section", {"id": self.topic["id"], "key": "understanding", "version_id": version["id"], "expected_revision": edit["revision"]})
        self.assertEqual(restored["body"], body)
        self.assertEqual(restored["sources"], original["sources"])
        export = self.store.action("export_workspace_note", {"kind": "learning_topic", "id": self.topic["id"]})
        text = Path(export["path"]).read_text()
        self.assertIn(body, text)
        self.assertIn("#message-" + self.answer["id"], text)
        self.assertIn("来源截止", text)

    def test_invalid_source_or_user_plan_does_not_replace_previous_report(self):
        first = self.generate()["report"]
        self.add_exchange("新问题", "新回答")
        output = self.output(); output["understanding"]["sources"] = ["message:invented"]
        view = self.generate(output)
        self.assertEqual(view["report"], first)
        self.assertEqual(view["state"], "failed")
        output = self.output(); output["next"]["owner"] = "user_plan"
        self.assertEqual(self.generate(output)["report"], first)

    def test_summary_uses_original_highlighted_messages_and_keeps_user_corrections_in_context(self):
        self.store.action("mark_learning_message", {"id": self.question["id"], "important": True})
        snapshot = self.store._summary_snapshot(self.topic["id"])
        source = snapshot["sources"]["message:" + self.question["id"]]
        self.assertTrue(source["important"])
        self.assertEqual(source["text"], self.question["content"])
        self.generate()
        self.store.action("edit_summary_section", {"id": self.topic["id"], "key": "goal", "expected_revision": 1, "body": "人工纠正的目标"})
        message = {**self.question, "sources": []}
        self.assertIn("人工纠正的目标", self.store._learning_prompt(self.topic, message, False))

    def test_failed_or_running_assistant_is_not_a_summary_fact(self):
        self.store.put("learning_message", {"topic_id": self.topic["id"], "role": "assistant", "content": "错误的未完成结论", "status": "Failed", "revision": 1})
        snapshot = self.store._summary_snapshot(self.topic["id"])
        self.assertNotIn("错误的未完成结论", str(snapshot["sources"]))

    def test_summary_retains_record_snapshot_after_edit_and_unlink(self):
        record = self.store.action("create_record", {"content": "原文：先练习参数透传"})
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        topic = self.store.get("learning_topic", self.topic["id"])
        self.question["sources"] = self.store._learning_sources(topic, [])
        self.store.put("learning_message", self.question)
        revised = self.store.action("update_record", {"id": record["id"], "expected_updated_at": record["updated_at"], "content": "改为练习关键字参数"})
        original_ref = f"record:{record['id']}:{record['revision']}"
        latest_ref = f"record:{record['id']}:{revised['revision']}"
        snapshot = self.store._summary_snapshot(topic["id"])
        self.assertEqual(record["content"], snapshot["sources"][original_ref]["text"])
        self.assertEqual(revised["content"], snapshot["sources"][latest_ref]["text"])
        self.assertEqual(self.question["id"], snapshot["sources"][original_ref]["message_id"])
        self.store.action("link_record", {"id": topic["id"], "record_id": record["id"], "remove": True})
        snapshot = self.store._summary_snapshot(topic["id"])
        self.assertEqual(record["content"], snapshot["sources"][original_ref]["text"])
        self.assertNotIn(latest_ref, snapshot["sources"])

    def test_historical_import_is_not_user_intent_and_clipping_is_visible(self):
        record = self.store.action("create_record", {"content": "资料" * 11000})
        record["source"] = {"kind": "obsidian"}
        self.store.put("record", record)
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        sources = self.store._learning_sources(self.store.get("learning_topic", self.topic["id"]), [])
        self.assertEqual("source", sources[0]["role"])
        self.assertTrue(sources[0]["partial"])
        # Older stored messages do not contain explicit role/partial metadata.
        sources[0].pop("role")
        sources[0].pop("partial")
        self.question["sources"] = sources
        self.store.put("learning_message", self.question)
        self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"], "remove": True})
        source = self.store._summary_snapshot(self.topic["id"])["sources"][f"record:{record['id']}:1"]
        self.assertEqual("source", source["role"])
        self.assertTrue(source["partial"])

    def test_invalid_restore_section_key_preserves_report(self):
        report = self.generate()["report"]
        self.store.action("edit_summary_section", {"id": self.topic["id"], "key": "goal", "body": "新目标", "expected_revision": 1})
        version = self.store.summary_view(self.topic["id"])["versions"][0]
        before = self.store.get("learning_summary", report["id"])
        for key in ([], {}, None, 42):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.action("restore_summary_section", {"id": self.topic["id"], "version_id": version["id"], "key": key})
        self.assertEqual(before, self.store.get("learning_summary", report["id"]))


if __name__ == "__main__":
    unittest.main()
