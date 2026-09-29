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
from server.runtime import RUNTIMES, Runtime, execute, say, stop_process, tool
from server.store import Store


class FakeRuntime(Runtime):
    id, label, binary = "fake", "假通道", "fake-agent"
    resumable = True

    def command(self, executable, workspace, output, prompt):
        return [executable, "--cwd", str(workspace)]

    def resume_args(self, session):
        return ["--resume", session]

    def progress(self, line, state):
        event = json.loads(line)
        state["external_id"] = event.get("session", state.get("external_id"))
        if "say" in event:
            say(state, event["say"])
        if "tool" in event:
            tool(state, event["tool"])
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
        self.task = self.store.action("create_task", {"title": "派出去", "project_id": project["id"], "runtime": "codex"})
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

    def first_turn(self):
        class Process(FakeAgentProcess):
            def behave(self, prompt):
                return lines({"session": "s-1", "say": "先看一下结构"}, {"tool": "Bash ls"}, {"say": "改好了"}, {"result": "改好了"}), "", 0

        run = self.wait_run(self.start(Process)["id"])
        self.assertEqual(run["transcript"], [{"type": "text", "text": "先看一下结构"}, {"type": "tool", "text": "Bash ls"}, {"type": "text", "text": "改好了"}])
        self.assertIsNone(run["message"])
        return run

    def test_follow_up_continues_the_same_session_with_only_the_new_message(self):
        self.first_turn()
        seen = {}

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                seen.update(command=self.command, prompt=prompt)
                return lines({"session": "s-1", "say": "测试也加上了"}), "", 0

        self.patch_runtime(Process)
        run = self.wait_run(self.store.action("send_agent_message", {"task_id": self.task["id"], "text": "再加个测试"})["id"])
        self.assertEqual(seen["command"][-2:], ["--resume", "s-1"])
        self.assertTrue(seen["prompt"].startswith("再加个测试"))
        self.assertNotIn("任务：派出去", seen["prompt"])
        self.assertEqual((run["message"], run["resumed"], run["status"]), ("再加个测试", True, "Finished"))
        self.assertEqual(self.store.get("task", self.task["id"])["status"], "Review")

    def test_lost_session_falls_back_to_a_new_one_that_carries_the_conversation(self):
        self.first_turn()
        attempts = []

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                attempts.append((self.command, prompt))
                if "--resume" in self.command:
                    return "", 'Session "s-1" not found\n', 1
                return lines({"session": "s-2", "say": "接上了"}), "", 0

        self.patch_runtime(Process)
        run = self.wait_run(self.store.action("send_agent_message", {"task_id": self.task["id"], "text": "再加个测试"})["id"])
        self.assertEqual(len(attempts), 2)
        self.assertNotIn("--resume", attempts[1][0])
        for text in ("任务：派出去", "此前的对话", "改好了", "用户的新消息：\n再加个测试"):
            self.assertIn(text, attempts[1][1])
        self.assertEqual((run["status"], run["resumed"], run["resume_failed"], run["external_id"]), ("Finished", False, True, "s-2"))
        self.assertIn("原会话无法续接，已开新会话并附上之前的对话", run["log_tail"])

    def test_messages_need_a_finished_turn_and_failed_turns_can_still_be_accepted(self):
        with self.assertRaisesRegex(ValueError, "Agent 回复后"):
            self.store.action("send_agent_message", {"task_id": self.task["id"], "text": "你好"})

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                return "", "boom\n", 1

        self.wait_run(self.start(Process)["id"])
        self.assertEqual(self.store.get("task", self.task["id"])["status"], "Blocked")
        with self.assertRaisesRegex(ValueError, "消息"):
            self.store.action("send_agent_message", {"task_id": self.task["id"], "text": "  "})
        task = self.store.action("review_agent", {"task_id": self.task["id"], "choice": "approve"})
        self.assertEqual(task["status"], "Done")

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

            def command(self, executable, workspace, output, prompt):
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


FIXTURES = Path(__file__).parent / "fixtures"


def feed(runtime, workspace, text):
    state, logs = {"workspace": Path(workspace).resolve()}, []
    for line in text.splitlines(True):
        log = runtime.progress(line, state)
        if log:
            logs.append(log)
    return state, logs


class DirectRuntimeTests(unittest.TestCase):
    """Kimi samples and the Claude Code error sample are real output recorded in /tmp trial runs."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_kimi_sample_yields_session_log_and_result(self):
        state, logs = feed(RUNTIMES["kimi"], self.workspace, (FIXTURES / "kimi-stream-success.jsonl").read_text())
        self.assertTrue(state["external_id"].startswith("session_"))
        self.assertEqual(state["result"], "已在当前目录创建 hello.txt，内容为 hi 一行。")
        self.assertIn("Write hello.txt", logs)
        self.assertNotIn("outside_writes", state)

    def test_kimi_write_outside_workspace_is_flagged_even_when_blocked(self):
        state, logs = feed(RUNTIMES["kimi"], self.workspace, (FIXTURES / "kimi-stream-outside-blocked.jsonl").read_text())
        self.assertEqual(state["outside_writes"], [str(Path("/tmp/pos-trial/outside/escape.txt").resolve())])
        self.assertIn("↳ write failed: permission denied", logs)

    def test_claude_error_result_fails_even_with_success_subtype(self):
        state, logs = feed(RUNTIMES["claude"], self.workspace, (FIXTURES / "claude-stream-api-error.jsonl").read_text())
        self.assertIn("余额不足", state["error"])
        self.assertEqual(state["external_id"], "b0de6e1a-d9de-4595-a0e5-353f37cbb1c3")
        self.assertEqual(logs[:2], ["已启动 · glm-5.2", "接口重试 1/10（429）"])

    def test_claude_tool_use_is_logged_and_outside_edits_flagged(self):
        # Hand-written from the documented stream-json shape; not yet seen from a real successful run.
        outside = str(Path("/tmp/elsewhere.txt").resolve())
        sample = lines(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "先写文件"},
                                                           {"type": "tool_use", "name": "Write", "input": {"file_path": str(self.workspace / "a.txt")}}]}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/tmp/elsewhere.txt"}},
                                                           {"type": "tool_use", "name": "Bash", "input": {"command": "npm test"}}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "完成", "session_id": "s-2"},
        )
        state, logs = feed(RUNTIMES["claude"], self.workspace, sample)
        self.assertEqual((state["result"], state["external_id"], state["outside_writes"]), ("完成", "s-2", [outside]))
        self.assertEqual(logs[1], "Edit /tmp/elsewhere.txt · Bash npm test")
        self.assertNotIn("error", state)


class SandboxedRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.store = Store(self.root / "test.sqlite3")
        project = self.store.action("create_project", {"name": "项目", "workspace_path": str(self.workspace)})
        self.task = self.store.action("create_task", {"title": "派给 Kimi", "project_id": project["id"], "executor_type": "agent", "runtime": "kimi"})
        self.sandbox = self.root / "sandbox-exec"
        self.sandbox.write_text("")
        for patcher in (patch("server.runtime.shutil.which", return_value="/bin/kimi"), patch("server.runtime.SANDBOX_EXEC", str(self.sandbox))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def wait_run(self, run_id):
        for _ in range(300):
            run = self.store.get("agent_run", run_id)
            if run["status"] != "Running" and run_id not in self.store._workers:
                return run
            time.sleep(0.01)
        self.fail("执行未结束")

    def test_kimi_runs_inside_sandbox_with_prompt_argument_and_records_outside_writes(self):
        seen = {}
        sample = (FIXTURES / "kimi-stream-outside-blocked.jsonl").read_text()

        class Process(FakeAgentProcess):
            def behave(self, prompt):
                seen.update(command=self.command, stdin=prompt)
                return sample, "", 0

        with patch("server.runtime.subprocess.Popen", Process):
            run = self.wait_run(self.store.action("start_agent", {"task_id": self.task["id"]})["id"])
        command = seen["command"]
        self.assertEqual(command[:2], [str(self.sandbox), "-p"])
        self.assertIn(f'(subpath "{self.workspace.resolve()}")', command[2])
        self.assertIn("deny file-write*", command[2])
        self.assertEqual(command[3:7], ["/bin/kimi", "--output-format", "stream-json", "-p"])
        self.assertIn("任务：派给 Kimi", command[7])
        self.assertEqual(seen["stdin"], "")
        self.assertEqual((run["status"], run["runtime"], run["agent_id"]), ("Finished", "kimi", "Kimi"))
        self.assertEqual(run["outside_writes"], [str(Path("/tmp/pos-trial/outside/escape.txt").resolve())])
        self.assertTrue(run["external_id"].startswith("session_"))
        self.assertEqual({entry["type"] for entry in run["transcript"]}, {"text", "tool"})
        self.assertEqual(RUNTIMES["kimi"].resume_args(run["external_id"]), ["-S", run["external_id"]])

    def test_missing_sandbox_refuses_to_run_unconfined(self):
        self.sandbox.unlink()
        with patch("server.runtime.subprocess.Popen") as popen:
            run = self.wait_run(self.store.action("start_agent", {"task_id": self.task["id"]})["id"])
        popen.assert_not_called()
        self.assertEqual(run["status"], "Failed")
        self.assertIn("已拒绝执行", run["error"])


@unittest.skipUnless(Path("/usr/bin/sandbox-exec").is_file(), "needs macOS sandbox-exec")
class RealSandboxTests(unittest.TestCase):
    def test_profile_allows_workspace_and_denies_other_writes(self):
        class Shell(Runtime):
            id, label = "shell", "Shell"
            state_paths, prompt_in_argv = [], True

            def command(self, executable, workspace, output, prompt):
                return [executable, "-c", prompt]

        probe = Path.home() / ".pos-escape-probe"
        self.addCleanup(probe.unlink, missing_ok=True)
        with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory(dir=Path.home()) as outside:
            scratch = Path(f"/tmp/pos-sandbox-probe-{os.getpid()}.txt")
            self.addCleanup(scratch.unlink, missing_ok=True)
            script = f"echo in > inside.txt; echo tmp > '{scratch}'; echo out > '{outside}/escape.txt'; echo home > \"$HOME/.pos-escape-probe\""
            outcome = execute(Shell(), "/bin/sh", script, Path(workspace), lambda p: None, lambda text: None)
            self.assertTrue((Path(workspace) / "inside.txt").exists())
            self.assertTrue(scratch.exists())
            self.assertFalse((Path(outside) / "escape.txt").exists())
            self.assertFalse(probe.exists())
            self.assertFalse(outcome.succeeded)
            self.assertIn("Operation not permitted", outcome.error)


if __name__ == "__main__":
    unittest.main()
