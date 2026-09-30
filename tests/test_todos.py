import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from server.store import Store, local_day
from server.todos import todo_order


class TodoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def todo(self, title="待办", **fields):
        return self.store.action("create_todo", {"title": title, **fields})

    def test_delete_todo_removes_it_everywhere(self):
        todo, kept = self.todo("要删的", today=True), self.todo("留下的")
        self.store.action("delete_todo", {"id": todo["id"]})
        self.assertEqual([t["id"] for t in self.store.all("todo")], [kept["id"]])
        self.assertEqual(self.store.today_todos(), [])
        self.assertEqual(self.store.events()[0]["type"], "TodoDeleted")
        with self.assertRaises(ValueError):
            self.store.action("delete_todo", {"id": todo["id"]})

    def test_priority_defaults_to_medium_and_is_validated(self):
        todo = self.todo()
        self.assertEqual(todo["priority"], "medium")
        self.assertEqual(self.store.action("update_todo", {"id": todo["id"], "priority": "high"})["priority"], "high")
        for bad in ("urgent", None):
            with self.assertRaises(ValueError):
                self.store.action("update_todo", {"id": todo["id"], "priority": bad})
        with self.assertRaises(ValueError):
            self.todo(priority="p0")

    def test_drag_reorders_within_and_across_columns(self):
        a, b, c = self.todo("a"), self.todo("b"), self.todo("c")
        pool = lambda: [t["title"] for t in sorted((t for t in self.store.all("todo") if not t.get("planned_date")), key=todo_order)]
        self.store.action("move_todo", {"id": c["id"], "today": False, "before_id": a["id"]})
        self.assertEqual(pool(), ["c", "a", "b"])
        self.store.action("move_todo", {"id": c["id"], "today": False, "before_id": None})
        self.assertEqual(pool(), ["a", "b", "c"])
        t1, t2 = self.todo("t1", today=True), self.todo("t2", today=True)
        self.store.action("move_todo", {"id": b["id"], "today": True, "before_id": t2["id"]})
        self.assertEqual([t["title"] for t in self.store.today_todos()], ["t1", "b", "t2"])
        self.store.action("move_todo", {"id": t1["id"], "today": False, "before_id": a["id"]})
        self.assertEqual(pool(), ["t1", "a", "c"])
        self.store.action("plan_todo", {"id": c["id"], "today": True})
        self.assertEqual([t["title"] for t in self.store.today_todos()], ["b", "t2", "c"])
        self.store.action("toggle_todo", {"id": b["id"]})
        with self.assertRaises(ValueError):
            self.store.action("move_todo", {"id": b["id"], "today": False})

    def test_reordering_today_keeps_carried_over_date(self):
        old = self.todo("昨天的", today=True)
        yesterday = (date.fromisoformat(local_day()) - timedelta(days=1)).isoformat()
        self.store.put("todo", {**self.store.get("todo", old["id"]), "planned_date": yesterday})
        fresh = self.todo("今天的", today=True)
        self.store.action("move_todo", {"id": old["id"], "today": True, "before_id": None})
        todos = self.store.today_todos()
        self.assertEqual([t["title"] for t in todos], ["今天的", "昨天的"])
        self.assertEqual(todos[1]["carried_days"], 1)
        self.assertEqual(fresh["planned_date"], local_day())

    def test_todos_from_before_ordering_stay_above_new_ones(self):
        legacy = self.todo("老的", today=True)
        self.store.put("todo", {key: value for key, value in self.store.get("todo", legacy["id"]).items() if key != "rank"})
        self.todo("新的", today=True)
        self.assertEqual([t["title"] for t in self.store.today_todos()], ["老的", "新的"])

    def test_dismissing_the_reminder_marks_today(self):
        self.store.action("dismiss_todo_reminder", {})
        self.assertEqual(self.store.state()["settings"]["todo_reminder_date"], local_day())

    def test_create_toggle_and_move_between_pool_and_today(self):
        pool = self.todo("池里的")
        today = self.todo("今天的", today=True, note="  备注  ")
        self.assertEqual((today["planned_date"], today["note"]), (local_day(), "备注"))
        self.assertEqual([t["id"] for t in self.store.today_todos()], [today["id"]])
        self.store.action("plan_todo", {"id": pool["id"], "today": True})
        self.store.action("plan_todo", {"id": today["id"], "today": False})
        self.assertEqual([t["id"] for t in self.store.today_todos()], [pool["id"]])
        done = self.store.action("toggle_todo", {"id": pool["id"]})
        self.assertTrue(done["done_at"])
        with self.assertRaisesRegex(ValueError, "已完成"):
            self.store.action("plan_todo", {"id": pool["id"], "today": False})
        self.assertEqual(self.store.today_todos()[0]["id"], pool["id"])
        self.assertIsNone(self.store.action("toggle_todo", {"id": pool["id"]})["done_at"])
        with self.assertRaises(ValueError):
            self.todo("   ")

    def test_unfinished_todos_carry_over_and_finished_ones_drop_off(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        carried = self.todo("昨天没做完", today=True)
        self.store.put("todo", {**self.store.get("todo", carried["id"]), "planned_date": yesterday})
        finished = self.todo("昨天做完", today=True)
        self.store.put("todo", {**self.store.get("todo", finished["id"]), "planned_date": yesterday, "done_at": yesterday + "T10:00:00+08:00"})
        fresh = self.todo("今天新加", today=True)
        view = self.store.today_todos()
        self.assertEqual([t["id"] for t in view], [carried["id"], fresh["id"]])
        self.assertEqual([t["carried_days"] for t in view], [1, 0])
        self.store.action("toggle_todo", {"id": fresh["id"]})
        self.assertEqual([t["id"] for t in self.store.today_todos()], [carried["id"], fresh["id"]])
        self.assertEqual([t["id"] for t in self.store.todos_for_day(yesterday)], [carried["id"], finished["id"]])

    def test_daily_log_reads_todo_completions_and_unfinished(self):
        done = self.todo("写完简历", today=True)
        undone = self.todo("复习数仓", today=True)
        flip = self.todo("点错了", today=True)
        self.store.action("toggle_todo", {"id": done["id"]})
        self.store.action("toggle_todo", {"id": flip["id"]})
        self.store.action("toggle_todo", {"id": flip["id"]})
        summary = self.store.action("draft_log", {})["summary"]
        completed, _, rest = summary.partition("## 明日工作计划")
        self.assertIn("写完简历", completed)
        self.assertNotIn("点错了", completed)
        self.assertIn("复习数仓", rest)
        self.assertIn("点错了", rest)
        self.todo("晚上新加")
        self.assertTrue(self.store.history(local_day())["log"]["stale"])

    def test_last_work_counts_completed_todos_under_their_project(self):
        project = self.store.action("create_project", {"name": "项目"})
        todo = self.todo("整理工作台", project_id=project["id"])
        self.store.action("toggle_todo", {"id": todo["id"]})
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.store.db.execute("UPDATE activity SET created_at=?", (yesterday + "T12:00:00+08:00",))
        self.store.db.commit()
        work = self.store.last_work()
        self.assertEqual(work["date"], yesterday)
        group = work["groups"][0]
        self.assertEqual((group["name"], group["tasks"][0]["title"], group["tasks"][0]["kind"]), ("项目", "整理工作台", "TodoCompleted"))

    def test_record_converts_to_a_single_todo(self):
        record = self.store.action("create_record", {"content": "整理简历问题\n补后端知识"})
        todo = self.store.action("record_to_todo", {"id": record["id"]})
        again = self.store.action("record_to_todo", {"id": record["id"]})
        self.assertEqual(todo["id"], again["id"])
        self.assertEqual((todo["record_id"], todo["note"], todo["planned_date"]), (record["id"], record["content"], None))

    def test_self_tasks_migrate_to_todos_once_with_backup(self):
        workspace = Path(self.temp.name) / "ws"
        workspace.mkdir()
        project = self.store.action("create_project", {"name": "项目", "workspace_path": str(workspace)})
        record = self.store.action("create_record", {"content": "来自记录"})

        def legacy(title, **fields):
            return self.store.put("task", {"title": title, "description": "", "status": "Inbox", "executor_type": "self", "runtime": None, "project_id": None, **fields})

        linked = legacy("来自记录", record_id=record["id"])
        self.store.put("record", {**record, "task_id": linked["id"]})
        inbox = legacy("准备面试", description="1.整理简历问题", project_id=project["id"])
        done = legacy("做完的", status="Done", completed_at="2026-09-28T10:00:00+08:00")
        agent = self.store.action("create_task", {"title": "Agent 任务", "project_id": project["id"], "runtime": "kimi"})
        self_with_run = legacy("跑过 Agent")
        self.store.put("agent_run", {"task_id": self_with_run["id"], "status": "Finished", "workspace_path": str(workspace)})
        self.store.close()

        self.store = Store(self.path)
        self.assertEqual({t["id"] for t in self.store.all("task")}, {agent["id"], self_with_run["id"]})
        todos = {t["migrated_from_task"]: t for t in self.store.all("todo")}
        self.assertEqual(set(todos), {linked["id"], inbox["id"], done["id"]})
        self.assertEqual((todos[inbox["id"]]["note"], todos[inbox["id"]]["project_id"], todos[inbox["id"]]["planned_date"]), ("1.整理简历问题", project["id"], None))
        self.assertTrue(todos[done["id"]]["done_at"])
        self.assertEqual(self.store.get("record", record["id"])["todo_id"], todos[linked["id"]]["id"])
        self.assertEqual(self.store.action("record_to_todo", {"id": record["id"]})["id"], todos[linked["id"]]["id"])
        self.assertEqual(len(self.store.backups()), 1)
        self.assertEqual(sum(e["type"] == "TaskMigratedToTodo" for e in self.store.events()), 3)
        self.store.close()

        self.store = Store(self.path)
        self.assertEqual(len(self.store.all("todo")), 3)
        self.assertEqual(len(self.store.backups()), 1)


if __name__ == "__main__":
    unittest.main()
