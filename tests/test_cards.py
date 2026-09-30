import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from server.runtime import RUNTIMES, Outcome
from server.store import Store, local_day


def days(n):
    return (date.fromisoformat(local_day()) + timedelta(days=n)).isoformat()


class FakeRuntime:
    id, label, remote = "fake", "Fake", False

    def __init__(self, result="", succeeded=True):
        self.result, self.succeeded, self.calls = result, succeeded, []

    def command_path(self, settings):
        return "/bin/fake"

    def run(self, executable, prompt, workspace, on_start, on_log, settings):
        self.calls.append((prompt, Path(workspace)))
        return Outcome(self.succeeded, result=self.result, error="" if self.succeeded else "额度不足")


class CardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "test.sqlite3")
        self.topic = self.store.action("create_learning_topic", {"title": "后端面试", "goal": "数据库与缓存"})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def card(self, front="什么是 MVCC？", back="多版本并发控制"):
        return self.store.action("create_card", {"topic_id": self.topic["id"], "front": front, "back": back})

    def fake(self, runtime):
        self.store.action("set_card_push", {"id": self.topic["id"], "card_engine": "kimi"})
        return patch.dict(RUNTIMES, {"kimi": runtime})

    def test_cards_can_be_written_edited_and_deleted(self):
        card = self.card()
        self.assertEqual((card["source"], card["due_date"], card["step"]), ("user", local_day(), 0))
        edited = self.store.action("update_card", {"id": card["id"], "front": "MVCC 解决什么问题？", "back": "读写不阻塞"})
        self.assertEqual((edited["front"], edited["back"]), ("MVCC 解决什么问题？", "读写不阻塞"))
        with self.assertRaises(ValueError):
            self.store.action("update_card", {"id": card["id"], "front": "  "})
        self.store.action("delete_card", {"id": card["id"]})
        self.assertEqual(self.store.all("learning_card"), [])

    def test_review_ladder_then_mastered_and_restore(self):
        card = self.card()
        review = lambda rating: self.store.action("review_card", {"id": card["id"], "rating": rating})
        self.assertEqual(review("forgot")["due_date"], days(1))
        self.assertEqual(review("fuzzy")["due_date"], days(3))
        self.assertEqual([(c["step"], c["due_date"]) for c in (review("remembered"), review("remembered"), review("remembered"))],
                         [(1, days(7)), (2, days(14)), (3, days(30))])
        mastered = review("remembered")
        self.assertTrue(mastered["mastered_at"])
        self.assertIsNone(mastered["due_date"])
        self.assertEqual(len(mastered["reviews"]), 6)
        with self.assertRaisesRegex(ValueError, "先恢复"):
            review("remembered")
        restored = self.store.action("restore_card", {"id": card["id"]})
        self.assertEqual((restored["mastered_at"], restored["step"], restored["due_date"]), (None, 0, days(1)))
        self.assertEqual(review("forgot")["step"], 0)
        with self.assertRaises(ValueError):
            review("maybe")

    def test_push_settings_are_validated(self):
        topic = self.store.action("set_card_push", {"id": self.topic["id"], "push_enabled": True, "daily_count": 5, "card_engine": "cursor"})
        self.assertEqual((topic["push_enabled"], topic["daily_count"], topic["card_engine"]), (True, 5, "cursor"))
        for payload in ({"daily_count": 0}, {"daily_count": 11}, {"daily_count": True}, {"card_engine": "multica"}, {"card_engine": "nope"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.store.action("set_card_push", {"id": self.topic["id"], **payload})

    def test_generation_parses_messy_output_skips_duplicates_and_runs_in_a_temp_dir(self):
        self.card("什么是 MVCC？")
        output = '好的：\n```json\n[{"front": "什么是 MVCC？", "back": "重复"}, {"front": "Redis 为什么快？", "back": "内存 + 单线程"},' \
                 ' {"front": "什么是回表", "back": "二级索引再查主键"}, {"front": "  "}, "垃圾"]\n```'
        runtime = FakeRuntime(output)
        with self.fake(runtime):
            result = self.store.action("generate_cards", {"topic_id": self.topic["id"]})
        self.assertEqual([c["front"] for c in result["cards"]], ["Redis 为什么快？", "什么是回表"])
        self.assertEqual({(c["source"], c["engine"]) for c in result["cards"]}, {("ai", "Fake")})
        prompt, workspace = runtime.calls[0]
        self.assertIn("什么是 MVCC？", prompt)
        self.assertIn("出 3 张新卡片", prompt)
        self.assertFalse(workspace.exists())
        self.assertNotEqual(workspace, self.root)
        self.assertEqual(self.store.get("learning_topic", self.topic["id"]).get("last_push_date"), local_day())

    def test_manual_generation_blocks_concurrent_and_same_day_push(self):
        started, release = threading.Event(), threading.Event()

        class SlowRuntime(FakeRuntime):
            def run(self, *args):
                started.set()
                release.wait(5)
                return super().run(*args)

        runtime = SlowRuntime('[{"front": "a", "back": "b"}]')
        with self.fake(runtime):
            self.store.action("set_card_push", {"id": self.topic["id"], "push_enabled": True})
            worker = threading.Thread(target=self.store.action, args=("generate_cards", {"topic_id": self.topic["id"]}))
            worker.start()
            self.assertTrue(started.wait(5))
            with self.assertRaisesRegex(ValueError, "正在生成"):
                self.store.action("generate_cards", {"topic_id": self.topic["id"]})
            self.store.daily_card_push()
            release.set()
            worker.join(5)
            self.store.daily_card_push()
        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual([c["front"] for c in self.store.all("learning_card")], ["a"])

    def test_generation_uses_references_rules_and_records_basis(self):
        link = lambda record: self.store.action("link_record", {"id": self.topic["id"], "record_id": record["id"]})
        resume = self.store.action("create_record", {"title": "简历.md", "content": "负责订单系统的 Redis 缓存改造", "record_type": "resource"})
        notes = self.store.action("create_record", {"title": "旧笔记", "content": "不要用这份", "record_type": "resource"})
        pdf = self.store.action("create_record", {"title": "手册.pdf", "record_type": "resource"})
        for record in (resume, notes, pdf):
            link(record)
        self.store.action("add_material", {"record_id": pdf["id"], "name": "手册.pdf", "base64": "JVBERi0xLjQK"})
        self.store.action("set_card_source", {"id": self.topic["id"], "record_id": notes["id"], "enabled": False})
        self.store.action("set_card_rules", {"text": "答案用中文，先给结论"})
        runtime = FakeRuntime('[{"front": "缓存击穿怎么防？", "back": "互斥锁或逻辑过期", "basis": "简历.md"}]')
        with self.fake(runtime):
            result = self.store.action("generate_cards", {"topic_id": self.topic["id"]})
        prompt = runtime.calls[0][0]
        self.assertIn("<<<资料：简历.md>>>\n负责订单系统的 Redis 缓存改造", prompt)
        self.assertIn("答案用中文，先给结论", prompt)
        self.assertIn("资料外补充", prompt)
        self.assertNotIn("不要用这份", prompt)
        self.assertEqual(result["cards"][0]["basis"], "简历.md")
        self.assertIn("参考了 1 份资料", result["message"])
        self.assertIn("《手册.pdf》还没有提取文字", result["message"])
        with self.assertRaisesRegex(ValueError, "尚未关联"):
            self.store.action("set_card_source", {"id": self.topic["id"], "record_id": "missing", "enabled": True})
        self.store.action("set_card_source", {"id": self.topic["id"], "record_id": notes["id"], "enabled": True})
        self.assertEqual(self.store.get("learning_topic", self.topic["id"])["card_excluded_record_ids"], [])

    def test_failed_manual_generation_leaves_daily_push_pending(self):
        with self.fake(FakeRuntime(succeeded=False)), self.assertRaises(ValueError):
            self.store.action("generate_cards", {"topic_id": self.topic["id"]})
        self.assertIsNone(self.store.get("learning_topic", self.topic["id"]).get("last_push_date"))

    def test_failed_daily_push_records_error_once_per_day(self):
        with self.fake(FakeRuntime(succeeded=False)) as _:
            self.store.action("set_card_push", {"id": self.topic["id"], "push_enabled": True})
            self.store.daily_card_push()
            topic = self.store.get("learning_topic", self.topic["id"])
            self.assertEqual(topic["last_push_date"], local_day())
            self.assertIn("额度不足", topic["last_push_error"])
            with patch.object(self.store, "generate_cards") as generate:
                self.store.daily_card_push()
                generate.assert_not_called()
        with self.fake(FakeRuntime("不是 JSON")), self.assertRaisesRegex(ValueError, "不是卡片列表"):
            self.store.action("generate_cards", {"topic_id": self.topic["id"]})

    def test_daily_push_only_for_enabled_topics_and_clears_error(self):
        other = self.store.action("create_learning_topic", {"title": "没开推送"})
        runtime = FakeRuntime('[{"front": "a", "back": "b"}, {"front": "c", "back": "d"}]')
        with self.fake(runtime):
            self.store.action("set_card_push", {"id": self.topic["id"], "push_enabled": True, "daily_count": 1})
            self.store.put("learning_topic", {**self.store.get("learning_topic", self.topic["id"]), "last_push_error": "旧错误"})
            self.store.daily_card_push()
        topic = self.store.get("learning_topic", self.topic["id"])
        self.assertEqual((topic["last_push_date"], topic["last_push_error"]), (local_day(), None))
        self.assertEqual([c["front"] for c in self.store.all("learning_card")], ["a"])
        self.assertEqual(len(runtime.calls), 1)
        self.assertIsNone(self.store.get("learning_topic", other["id"]).get("last_push_date"))

    def test_obsidian_note_is_rewritten_with_the_days_cards(self):
        vault = self.root / "vault"
        vault.mkdir()
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        first = self.card("问题一", "解答一")
        self.card("问题二", "解答二")
        note = vault / "学习卡片" / f"{local_day()}.md"
        text = note.read_text()
        self.assertIn("## 后端面试", text)
        self.assertLess(text.index("### 问题一"), text.index("### 问题二"))
        self.assertIn("解答二", text)
        self.store.action("update_card", {"id": first["id"], "front": "问题一改", "back": "解答一"})
        self.assertIn("### 问题一改", note.read_text())
        for card in self.store.all("learning_card"):
            self.store.action("delete_card", {"id": card["id"]})
        self.assertFalse(note.exists())

    def test_obsidian_note_skips_symlinked_folder(self):
        vault, elsewhere = self.root / "vault", self.root / "elsewhere"
        vault.mkdir()
        elsewhere.mkdir()
        (vault / "学习卡片").symlink_to(elsewhere)
        self.store.action("save_settings", {"obsidian_vault": str(vault)})
        self.card()
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
