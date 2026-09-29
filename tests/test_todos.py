import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from server.store import Store, local_day


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
        completed, _, rest = summary.partition("未完成：")
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
        linked = self.store.action("record_to_task", {"id": record["id"]})
        inbox = self.store.action("create_task", {"title": "准备面试", "description": "1.整理简历问题", "project_id": project["id"]})
        done = self.store.action("create_task", {"title": "做完的"})
        self.store.action("complete_task", {"id": done["id"]})
        agent = self.store.action("create_task", {"title": "Agent 任务", "project_id": project["id"], "executor_type": "agent", "runtime": "kimi"})
        self_with_run = self.store.action("create_task", {"title": "跑过 Agent"})
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
