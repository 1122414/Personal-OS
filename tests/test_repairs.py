import json
import subprocess
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from server.store import Store, local_day


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "test.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def task(self, title="任务", **fields):
        return self.store.action("create_task", {"title": title, **fields})

    def test_late_events_block_confirmation_and_refresh_preserves_manual_draft(self):
        task = self.task()
        log = self.store.action("draft_log", {})
        self.store.action("update_log", {"id": log["id"], "summary": "用户的重要补充"})
        self.store.action("complete_task", {"id": task["id"]})
        self.assertTrue(self.store.history(local_day())["log"]["stale"])
        with self.assertRaisesRegex(ValueError, "新增事件"):
            self.store.action("confirm_log", {"id": log["id"]})
        refreshed = self.store.action("draft_log", {"regenerate": True})
        self.assertEqual(refreshed["revisions"][-1]["summary"], "用户的重要补充")
        self.assertIn("- 任务", refreshed["summary"])
        self.assertFalse(self.store.history(local_day())["log"]["stale"])
        self.store.action("confirm_log", {"id": log["id"]})
        with self.assertRaisesRegex(ValueError, "已经确认"):
            self.store.action("draft_log", {"regenerate": True})

    def test_manual_acknowledgement_rejects_events_arriving_during_edit(self):
        log = self.store.action("draft_log", {})
        self.task("first")
        shown = self.store.history(local_day())["log"]
        self.task("later")
        with self.assertRaisesRegex(ValueError, "新增事件"):
            self.store.action("update_log", {"id": log["id"], "summary": "checked", "acknowledge_events": True, "source_event_ids": shown["latest_source_event_ids"]})

    def test_brief_revalidates_tasks_and_uses_prior_confirmed_context(self):
        task = self.task()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.store.put("daily_log", {"date": yesterday, "summary": "CONFIRMED_PREVIOUS", "confirmed_at": yesterday})
        self.store.action("draft_log", {})
        channel = self.store.action("create_channel", {"name": "test"})
        item = self.store.action("create_intelligence", {"title": "IGNORE_SENTINEL", "source": "test", "channel_id": channel["id"], "why_recommended": "test"})
        self.store.action("feedback_intelligence", {"id": item["id"], "feedback": "ignore"})
        with patch("server.store.shutil.which", return_value="codex"), patch.object(self.store, "_codex_readonly", return_value=json.dumps({"priorities": [{"task_id": task["id"], "reason": "valid"}]})) as model:
            self.store.action("generate_brief", {})
        self.assertIn("CONFIRMED_PREVIOUS", model.call_args.args[0])
        self.assertNotIn("IGNORE_SENTINEL", model.call_args.args[0])
        self.store.action("complete_task", {"id": task["id"]})
        self.assertEqual(self.store.brief(), [])

    def test_blocked_tasks_remain_visible_in_daily_log(self):
        task = self.task()
        self.store.action("confirm_plan", {"task_ids": [task["id"]]})
        self.store.put("task", {**self.store.get("task", task["id"]), "status": "Blocked"})
        self.assertIn("阻塞与执行异常", self.store.action("draft_log", {})["summary"])

    def test_history_reads_beyond_recent_event_window_and_backfills(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.store.event("TaskCompleted", details={"title": "历史完成"})
        self.store.db.execute("UPDATE activity SET created_at=?", (yesterday + "T12:00:00+08:00",))
        self.store.db.commit()
        for _ in range(1001):
            self.store.event("TaskUpdated")
        self.assertEqual(len(self.store.state()["events"]), 1000)
        self.assertEqual(len(self.store.history(yesterday)["events"]), 1)
        self.assertIn(yesterday, self.store.history_dates())
        log = self.store.action("draft_log", {"date": yesterday})
        self.assertIn("历史完成", log["summary"])
        self.store.action("confirm_log", {"id": log["id"]})
        with self.assertRaises(ValueError):
            self.store.history("2099-01-01")

    def test_project_pulse_becomes_stale_after_task_progress(self):
        project = self.store.action("create_project", {"name": "project"})
        with patch.object(self.store, "_codex_readonly", return_value="current"):
            pulse = self.store.action("generate_project_pulse", {"id": project["id"]})
        self.assertFalse(self.store.pulse_stale(pulse))
        self.task(project_id=project["id"])
        self.assertTrue(self.store.pulse_stale(pulse))

    def test_failed_and_canceled_runs_keep_evidence_and_agent_constraints(self):
        for canceled in (False, True):
            with self.subTest(canceled=canceled):
                workspace = self.root / str(canceled)
                workspace.mkdir()
                project = self.store.action("create_project", {"name": "项目", "workspace_path": str(workspace)})
                self.store.action("create_decision", {"title": "DECISION_SENTINEL", "project_id": project["id"]})
                self.store.action("create_rule", {"text": "RULE_SENTINEL", "category": "Agent"})
                task = self.task(project_id=project["id"], executor_type="agent")
                started, stopped = threading.Event(), threading.Event()
                prompts = []

                class Process:
                    returncode = None

                    def __init__(self, *_args, **_kwargs):
                        pass

                    def communicate(self, prompt, timeout):
                        prompts.append(prompt)
                        (workspace / "partial.txt").write_text("actual change")
                        started.set()
                        if canceled:
                            stopped.wait(3)
                        self.returncode = -15 if canceled else 1
                        return "", "failure"

                    def terminate(self):
                        stopped.set()

                    def poll(self):
                        return self.returncode

                with patch("server.store.shutil.which", return_value="codex"), patch("server.store.subprocess.Popen", Process):
                    run = self.store.action("start_agent", {"task_id": task["id"]})
                    self.assertTrue(started.wait(2))
                    if canceled:
                        self.store.action("cancel_agent", {"id": run["id"]})
                    worker = self.store._workers.get(run["id"])
                    if worker:
                        worker.join(3)
                evidence = [a for a in self.store.all("artifact") if a["agent_run_id"] == run["id"]]
                self.assertEqual([a["name"] for a in evidence], ["partial.txt"])
                self.assertEqual(self.store.get("task", task["id"])["status"], "Blocked")
                self.assertIn("DECISION_SENTINEL", prompts[0])
                self.assertIn("RULE_SENTINEL", prompts[0])

    def test_plan_revisions_preserve_order_and_running_work(self):
        a, b = self.task("A"), self.task("B")
        self.store.action("confirm_plan", {"task_ids": [a["id"], b["id"]]})
        plan = self.store.action("revise_plan", {"task_ids": [b["id"], a["id"]]})
        self.assertEqual(plan["task_ids"], [b["id"], a["id"]])
        self.store.action("revise_plan", {"task_ids": [a["id"]]})
        self.assertEqual(self.store.get("task", b["id"])["status"], "Inbox")
        self.store.action("complete_task", {"id": a["id"]})
        with self.assertRaises(ValueError):
            self.store.action("revise_plan", {"task_ids": []})

    def test_restart_recovers_running_and_canceled_evidence_once(self):
        workspace = self.root / "workspace"
        workspace.mkdir()
        task = self.task()
        for status in ("Running", "Canceled"):
            self.store.put("agent_run", {"task_id": task["id"], "status": status, "workspace_path": str(workspace), "before_snapshot": {}})
        (workspace / "partial.txt").write_text("unreviewed")
        self.store.put("task", {**task, "status": "Running"})
        self.store.close()
        self.store = Store(self.root / "test.sqlite3")
        self.assertEqual(self.store.get("task", task["id"])["status"], "Blocked")
        artifacts = self.store.all("artifact")
        self.assertEqual(len(artifacts), 2)
        self.assertTrue(all(item["recovered"] for item in artifacts))
        self.store._recover_interrupted_runs()
        self.assertEqual(len(self.store.all("artifact")), 2)

    def test_timeout_keeps_partial_file_evidence(self):
        workspace = self.root / "timeout"
        workspace.mkdir()
        project = self.store.action("create_project", {"name": "timeout", "workspace_path": str(workspace)})
        task = self.task(project_id=project["id"], executor_type="agent")

        class Process:
            returncode = None

            def __init__(self, *_args, **_kwargs):
                pass

            def communicate(self, prompt=None, timeout=None):
                if timeout:
                    (workspace / "partial.txt").write_text("partial")
                    raise subprocess.TimeoutExpired("codex", timeout)
                return "", ""

            def kill(self):
                self.returncode = -9

        with patch("server.store.shutil.which", return_value="codex"), patch("server.store.subprocess.Popen", Process):
            run = self.store.action("start_agent", {"task_id": task["id"]})
            worker = self.store._workers.get(run["id"])
            if worker:
                worker.join(3)
        self.assertEqual(self.store.get("agent_run", run["id"])["error"], "Codex 执行超时")
        self.assertEqual(self.store.all("artifact")[0]["name"], "partial.txt")

    def test_feed_preserves_publication_date_and_records_source_errors(self):
        channel = self.store.action("create_channel", {"name": "feed", "sources": "https://example.com/feed"})
        entries = [{"title": "old", "summary": "", "url": "https://example.com/a", "published": "Mon, 01 Jan 2024 00:00:00 GMT"}]
        with patch("server.store.fetch_feed", return_value=entries):
            self.store.action("refresh_channel", {"id": channel["id"]})
        self.assertEqual(self.store.all("intelligence_item")[0]["published_at"][:10], "2024-01-01")
        with patch("server.store.fetch_feed", side_effect=OSError("offline")):
            result = self.store.action("refresh_channel", {"id": channel["id"]})
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self.store.get("intelligence_channel", channel["id"])["last_refresh"]["errors"][0]["error"], "offline")

    def test_archive_reopen_and_backup_restore_preserve_recovery_copy(self):
        task = self.task("keep")
        self.store.action("archive_task", {"id": task["id"]})
        self.assertEqual(self.store.brief(), [])
        with self.assertRaises(ValueError):
            self.store.action("complete_task", {"id": task["id"]})
        self.store.action("archive_task", {"id": task["id"], "restore": True})
        self.store.action("complete_task", {"id": task["id"]})
        self.store.action("reopen_task", {"id": task["id"]})
        backup = self.store.action("create_backup", {})
        later = self.task("later")
        exported = self.store.action("export_data", {})
        self.assertEqual(len(json.loads(Path(exported["path"]).read_text())["objects"]["task"]), 2)
        result = self.store.action("restore_backup", {"id": backup["id"]})
        self.assertIsNone(self.store.get("task", later["id"]))
        self.assertIsNotNone(self.store.get("task", task["id"]))
        self.store.action("restore_backup", {"id": result["previous_backup"]})
        self.assertIsNotNone(self.store.get("task", later["id"]))
        with self.assertRaises(ValueError):
            self.store.action("restore_backup", {"id": "../test.sqlite3"})
        self.store._active_jobs = 1
        with self.assertRaisesRegex(ValueError, "等待"):
            self.store.action("restore_backup", {"id": backup["id"]})
        self.store._active_jobs = 0
