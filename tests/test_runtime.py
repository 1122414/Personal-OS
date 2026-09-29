from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_fakes import FakeAgentProcess
from server.runtime import RUNTIMES, Runtime, execute, stop_process
from server.store import Store


class FakeRuntime(Runtime):
    id, label, binary = "fake", "假通道", "fake-agent"

    def command(self, executable, workspace, output):
        return [executable, "--cwd", str(workspace)]

    def progress(self, line, state):
        event = json.loads(line)
        state["external_id"] = event.get("session", state.get("external_id"))
        if "result" in event:
            state["result"] = event["result"]
        if "error" in event:
            state["error"] = event["error"]
        return event.get("log")


def lines(*events):
    return "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.store = Store(self.root / "test.sqlite3")
        project = self.store.action("create_project", {"name": "项目", "workspace_path": str(self.workspace)})
        self.task = self.store.action("create_task", {"title": "派出去", "project_id": project["id"], "executor_type": "agent"})
        patcher = patch.dict(RUNTIMES, {"fake": FakeRuntime()})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def patch_runtime(self, process_class, which="/bin/fake-agent"):
        for patcher in (patch("server.runtime.shutil.which", return_value=which), patch("server.runtime.subprocess.Popen", process_class)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def start(self, process_class, **payload):
        self.patch_runtime(process_class)
        return self.store.action("start_agent", {"task_id": self.task["id"], "runtime": "fake", **payload})

    def wait_run(self, run_id, statuses=("Finished", "Failed", "Canceled")):
        for _ in range(300):
            run = self.store.get("agent_run", run_id)
            if run["status"] in statuses and run_id not in self.store._workers:
                return run
            time.sleep(0.01)
        self.fail("执行未结束")

    def test_run_streams_log_records_session_and_waits_for_review(self):
        workspace = self.workspace

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                (workspace / "done.txt").write_text("ok")
                return lines({"session": "s-1", "log": "读取任务"}, {"log": "修改 done.txt"}, {"result": "完成并验证"}), "", 0

        run = self.wait_run(self.start(Process)["id"])
        self.assertEqual((run["status"], run["runtime"], run["agent_id"], run["external_id"]), ("Finished", "fake", "假通道", "s-1"))
        self.assertEqual(run["log_tail"], ["读取任务", "修改 done.txt"])
        self.assertEqual(run["result"], "完成并验证")
        task = self.store.get("task", self.task["id"])
        self.assertEqual((task["status"], task["runtime"], task["agent_id"]), ("Review", "fake", "假通道"))
        self.assertEqual([a["name"] for a in self.store.all("artifact")], ["done.txt"])

    def test_rerun_after_review_uses_the_same_runtime(self):
        class Process(FakeAgentProcess):
            def behave(self, prompt):
                return lines({"result": "第一次"}), "", 0

        self.wait_run(self.start(Process)["id"])
        rerun = self.store.action("review_agent", {"task_id": self.task["id"], "choice": "revise", "instruction": "补测试"})
        self.assertEqual(self.wait_run(rerun["id"])["runtime"], "fake")

    def test_nonzero_exit_or_reported_error_fails_and_blocks(self):
        cases = [(lines({"log": "开始"}), "boom\n", 1, "boom"), (lines({"error": "额度用完"}), "", 0, "额度用完")]
        for stdout, stderr, code, message in cases:
            with self.subTest(message=message):
                class Process(FakeAgentProcess):
                    def behave(self, prompt):
                        return stdout, stderr, code

                run = self.wait_run(self.start(Process)["id"])
                self.assertEqual(run["status"], "Failed")
                self.assertIn(message, run["error"])
                self.assertEqual(self.store.get("task", self.task["id"])["status"], "Blocked")

    def test_cancel_stops_the_process_and_keeps_log(self):
        started = threading.Event()

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                started.set()
                self.stopped.wait(3)
                return lines({"log": "被取消前的进度"}), "", -15

        run = self.start(Process)
        self.assertTrue(started.wait(2))
        self.store.action("cancel_agent", {"id": run["id"]})
        run = self.wait_run(run["id"], ("Canceled",))
        self.assertEqual(run["log_tail"], ["被取消前的进度"])
        self.assertEqual(self.store.get("task", self.task["id"])["status"], "Blocked")

    def test_restart_marks_a_running_direct_run_interrupted(self):
        started = threading.Event()

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                started.set()
                self.stopped.wait(3)
                return "", "", -15

        run = self.start(Process)
        self.assertTrue(started.wait(2))
        self.store.close()
        self.store = Store(self.root / "test.sqlite3")
        self.assertEqual(self.store.get("agent_run", run["id"])["status"], "Interrupted")
        self.assertEqual(self.store.get("task", self.task["id"])["status"], "Blocked")

    def test_missing_or_unknown_runtime_is_rejected_before_running(self):
        with patch("server.runtime.shutil.which", return_value=None), self.assertRaisesRegex(ValueError, "本机未找到 假通道 命令行"):
            self.store.action("start_agent", {"task_id": self.task["id"], "runtime": "fake"})
        with self.assertRaisesRegex(ValueError, "未知的执行通道"):
            self.store.action("start_agent", {"task_id": self.task["id"], "runtime": "nope"})
        self.assertEqual(self.store.all("agent_run"), [])

    def test_configured_command_path_is_validated_and_used(self):
        with self.assertRaisesRegex(ValueError, "找不到 Codex 命令"):
            self.store.action("save_settings", {"codex_command": str(self.root / "missing")})
        codex = self.root / "bin" / "codex-internal"
        codex.parent.mkdir()
        codex.write_text("#!/bin/sh\n")
        codex.chmod(codex.stat().st_mode | stat.S_IXUSR)
        self.store.action("save_settings", {"codex_command": str(codex)})
        with patch("server.runtime.shutil.which", return_value=None):
            status = self.store.state()["runtime"]
            self.assertTrue(status["codex_available"])
            self.assertEqual(self.store.codex_command(), str(codex))
        commands = []

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                commands.append(self.command)
                return "", "", 0

        self.patch_runtime(Process, which=None)
        run = self.store.action("start_agent", {"task_id": self.task["id"], "runtime": "codex"})
        self.wait_run(run["id"])
        self.assertEqual(commands[0][0], str(codex))

    def test_stop_process_ends_tools_the_agent_spawned(self):
        class Shell(Runtime):
            id, label = "shell", "Shell"

            def command(self, executable, workspace, output):
                return [executable, "-c", "sleep 30 & echo $!; wait"]

            def progress(self, line, state):
                state.setdefault("child", int(line))
                return line.strip()

        started, holder, outcome = threading.Event(), {}, {}
        runtime = Shell()

        def run():
            outcome["value"] = execute(runtime, "/bin/sh", "", self.workspace, lambda p: holder.setdefault("process", p), lambda text: (holder.setdefault("child", int(text)), started.set()))

        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(started.wait(5))
        stop_process(holder["process"])
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(outcome["value"].succeeded)
        for _ in range(100):
            try:
                os.kill(holder["child"], 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            self.fail("子进程仍在运行")


if __name__ == "__main__":
    unittest.main()
