"""Agent runtimes: how each agent CLI is launched and how its output is read.

Personal OS owns tasks, runs and review. A runtime only knows its command line
and output format, so adding or replacing an agent never touches that data.
Every run gets its own process group so cancel and timeout also stop the tools
the agent spawned. Agent CLIs without their own write sandbox run under
sandbox-exec, which only lets them write inside the workspace, their own state
directory and the temp directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

RUN_TIMEOUT = 3600
STDOUT_LIMIT = 2_000_000
ERROR_LIMIT = 4000
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
OUTSIDE_LIMIT = 50


def resolve_command(value: str) -> str | None:
    """A bare name is looked up on PATH; anything with a slash must be an executable file."""
    value = (value or "").strip()
    if not value:
        return None
    if "/" in value:
        path = Path(value).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(value)


def stop_process(process: Any, sig: int = signal.SIGTERM) -> None:
    try:
        os.killpg(process.pid, sig)
    except (AttributeError, TypeError, ProcessLookupError, PermissionError):
        (process.kill if sig == signal.SIGKILL else process.terminate)()


@dataclass
class Outcome:
    succeeded: bool
    result: str = ""
    error: str = ""
    external_id: str = ""
    outside_writes: list[str] | None = None
    detached: bool = False


def _sandbox_string(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _regex_literal(text: str) -> str:
    return re.sub(r"([.^$*+?()[\]{}|\\])", r"\\\1", text)


def sandbox_profile(workspace: Path, state_paths: list[str]) -> str:
    """Deny every file write except the workspace, the agent's own state and temp files."""
    home = str(Path.home().resolve())
    allowed = [f"(subpath {_sandbox_string(str(workspace.resolve()))})",
               f"(subpath {_sandbox_string(str(Path(tempfile.gettempdir()).resolve()))})",
               '(regex #"^/dev/")']
    allowed += [f'(regex #"^{_regex_literal(home + "/" + prefix)}")' for prefix in state_paths]
    return f"(version 1)(allow default)(deny file-write*)(allow file-write* {' '.join(allowed)})"


def note_write(state: dict[str, Any], path: Any) -> None:
    """Remember a tool write that targets a path outside the workspace (shown in review)."""
    if not isinstance(path, str) or not path.strip():
        return
    workspace = state["workspace"]
    target = (workspace / Path(path).expanduser()).resolve()
    if target.is_relative_to(workspace):
        return
    outside = state.setdefault("outside_writes", [])
    if str(target) not in outside and len(outside) < OUTSIDE_LIMIT:
        outside.append(str(target))


def _brief(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _tool_line(name: str, arguments: dict[str, Any], state: dict[str, Any]) -> str:
    path = next((arguments.get(key) for key in ("file_path", "path", "notebook_path") if arguments.get(key)), None)
    if re.search(r"write|edit", name, re.I):
        note_write(state, path)
    detail = path or arguments.get("command") or arguments.get("pattern") or arguments.get("description") or ""
    return _brief(f"{name} {detail}".strip())


class Runtime:
    id = ""
    label = ""
    binary = ""
    state_paths: list[str] | None = None
    prompt_in_argv = False
    remote = False

    @property
    def setting(self) -> str:
        return f"{self.id}_command"

    def command_path(self, settings: dict[str, Any]) -> str | None:
        return resolve_command(settings.get(self.setting) or self.binary)

    @property
    def sandboxed(self) -> bool:
        return self.state_paths is not None

    def command(self, executable: str, workspace: Path, output: Path, prompt: str) -> list[str]:
        raise NotImplementedError

    def run(self, executable: str, prompt: str, workspace: Path, on_start: Callable[[Any], None],
            on_log: Callable[[str], None], settings: dict[str, Any], external_id: str = "", rerun: bool = False,
            on_external_id: Callable[[str], None] = lambda _: None) -> Outcome:
        return execute(self, executable, prompt, workspace, on_start, on_log)

    def progress(self, line: str, state: dict[str, Any]) -> str | None:
        """Turn one stdout line into a log line; may record result/error/external_id in state."""
        return line.strip() or None

    def result(self, state: dict[str, Any], stdout: str, output: Path) -> str:
        return state.get("result") or stdout


class CodexRuntime(Runtime):
    id, label, binary = "codex", "Codex", "codex"

    def command(self, executable: str, workspace: Path, output: Path, prompt: str) -> list[str]:
        return [executable, "exec", "--ephemeral", "--skip-git-repo-check", "-s", "workspace-write",
                "-C", str(workspace), "-o", str(output), "-"]

    def result(self, state: dict[str, Any], stdout: str, output: Path) -> str:
        return output.read_text(encoding="utf-8") if output.exists() else stdout


class KimiRuntime(Runtime):
    """kimi -p stream-json: one JSON message per line; the prompt must be an argument."""
    id, label, binary = "kimi", "Kimi", "kimi"
    state_paths = [".kimi-code/"]
    prompt_in_argv = True

    def command(self, executable: str, workspace: Path, output: Path, prompt: str) -> list[str]:
        return [executable, "--output-format", "stream-json", "-p", prompt]

    def progress(self, line: str, state: dict[str, Any]) -> str | None:
        event = _json(line)
        if event is None:
            return _brief(line) or None
        if event.get("type") == "session.resume_hint":
            state["external_id"] = event.get("session_id") or state.get("external_id")
            return None
        if event.get("role") == "assistant":
            parts = []
            if event.get("content"):
                state["result"] = event["content"]
                parts.append(_brief(event["content"]))
            for call in event.get("tool_calls") or []:
                function = call.get("function") or {}
                arguments = _json(function.get("arguments") or "") or {}
                parts.append(_tool_line(function.get("name") or "工具", arguments, state))
            return " · ".join(parts) or None
        if event.get("role") == "tool":
            return _brief(f"↳ {event.get('content')}")
        return None


class ClaudeRuntime(Runtime):
    """claude -p stream-json. Edits are auto-accepted and Bash is allowed; sandbox-exec keeps both inside the workspace."""
    id, label, binary = "claude", "Claude Code", "claude"
    state_paths = [".claude"]

    def command(self, executable: str, workspace: Path, output: Path, prompt: str) -> list[str]:
        return [executable, "-p", "--output-format", "stream-json", "--verbose",
                "--allowed-tools", "Bash", "--permission-mode", "acceptEdits"]

    def progress(self, line: str, state: dict[str, Any]) -> str | None:
        event = _json(line)
        if event is None:
            return _brief(line) or None
        kind, subtype = event.get("type"), event.get("subtype")
        if event.get("session_id"):
            state["external_id"] = event["session_id"]
        if kind == "system" and subtype == "init":
            return f"已启动 · {event.get('model') or '默认模型'}"
        if kind == "system" and subtype == "api_retry":
            return f"接口重试 {event.get('attempt')}/{event.get('max_retries')}（{event.get('error_status') or event.get('error')}）"
        if kind == "assistant":
            parts = []
            for item in (event.get("message") or {}).get("content") or []:
                if item.get("type") == "text" and item.get("text"):
                    parts.append(_brief(item["text"]))
                elif item.get("type") == "tool_use":
                    parts.append(_tool_line(item.get("name") or "工具", item.get("input") or {}, state))
            return " · ".join(parts) or None
        if kind == "result":
            state["result"] = event.get("result") or ""
            if event.get("is_error"):
                state["error"] = event.get("result") or "Claude Code 执行失败"
            return None
        return None


class MulticaHandle:
    """Stands in for a process: cancel asks the Multica server to stop; detach only stops polling."""

    def __init__(self, base: list[str]):
        self.base, self.issue, self.task = base, "", ""
        self.cancelled, self.detached, self.wake = threading.Event(), threading.Event(), threading.Event()

    def poll(self) -> int | None:
        return 0 if self.cancelled.is_set() or self.detached.is_set() else None

    def terminate(self) -> None:
        if self.cancelled.is_set():
            return
        self.cancelled.set()
        self.wake.set()
        if self.task:
            threading.Thread(target=_multica, args=(self.base, "issue", "cancel-task", self.task, "--issue", self.issue), daemon=True).start()

    kill = terminate

    def detach(self) -> None:
        self.detached.set()
        self.wake.set()


def _multica(base: list[str], *args: str, stdin: str | None = None) -> Any:
    done = subprocess.run([*base, *args, "--output", "json"], input=stdin, capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise RuntimeError(_brief(done.stderr or done.stdout, 300) or f"退出码 {done.returncode}")
    return json.loads(done.stdout) if done.stdout.strip() else None


def _items(value: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = next((value[key] for key in keys if isinstance(value.get(key), list)), [])
    return [item for item in value or [] if isinstance(item, dict)]


class MulticaRuntime(Runtime):
    """Open-source Multica, driven only through its CLI JSON output.

    The JSON field names below come from hand-written samples and have not yet
    been checked against a real Multica server.
    """
    id, label, binary = "multica", "Multica", "multica"
    remote = True
    poll_seconds = 5.0
    DONE = {"completed", "complete", "succeeded", "success", "done", "finished"}
    FAILED = {"failed", "error", "errored", "cancelled", "canceled", "timeout", "timed_out"}

    def command_path(self, settings: dict[str, Any]) -> str | None:
        if not (settings.get("multica_agent") or "").strip():
            return None
        return resolve_command(settings.get(self.setting) or "")

    def run(self, executable, prompt, workspace, on_start, on_log, settings, external_id="", rerun=False, on_external_id=lambda _: None):
        base = [executable, *(["--profile", settings["multica_profile"]] if settings.get("multica_profile") else [])]
        handle = MulticaHandle(base)
        handle.issue = external_id
        on_start(handle)
        state: dict[str, Any] = {"workspace": workspace.resolve()}
        try:
            seen: set[str] = set()
            if rerun and external_id:
                seen = {str(item.get("id")) for item in _items(_multica(base, "issue", "runs", external_id), "runs", "data", "items")}
                _multica(base, "issue", "rerun", external_id)
                on_log(f"已请求 Multica 重跑 {external_id}")
            elif not external_id:
                title = prompt.splitlines()[0].removeprefix("任务：").strip()[:200] or "Personal OS 任务"
                created = _multica(base, "issue", "create", "--title", title, "--description-stdin",
                                   "--assignee", settings["multica_agent"], stdin=f"{prompt}\n\nPersonal OS 本地工作目录：{workspace}")
                handle.issue = str((created or {}).get("id") or "")
                if not handle.issue:
                    raise RuntimeError("Multica 没有返回 issue 编号")
                on_external_id(handle.issue)
                on_log(f"已创建 Multica issue {(created or {}).get('identifier') or handle.issue}，指派给 {settings['multica_agent']}")
            return self._follow(base, handle, seen, state, on_log)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return Outcome(False, error=f"Multica 调用失败：{exc}", external_id=handle.issue)

    def _follow(self, base, handle, seen, state, on_log) -> Outcome:
        since, deadline, issue = 0, time.monotonic() + RUN_TIMEOUT, handle.issue
        while True:
            if handle.detached.is_set():
                return Outcome(False, external_id=issue, detached=True)
            if handle.cancelled.is_set():
                return Outcome(False, error="已取消 Multica 执行", external_id=issue)
            runs = [item for item in _items(_multica(base, "issue", "runs", issue), "runs", "data", "items") if str(item.get("id")) not in seen]
            task = max(runs, key=lambda item: str(item.get("created_at") or item.get("started_at") or ""), default=None)
            if task:
                if handle.task != str(task.get("id")):
                    handle.task, since = str(task.get("id")), 0
                for message in _items(_multica(base, "issue", "run-messages", handle.task, "--issue", issue, "--since", str(since)), "messages", "data", "items"):
                    since = max(since, int(message.get("seq") or message.get("sequence") or since))
                    text = self._message(message, state)
                    if text:
                        on_log(text)
                status = str(task.get("status") or "").lower()
                extra = {"external_id": issue, "outside_writes": state.get("outside_writes")}
                if status in self.DONE:
                    return Outcome(True, result=state.get("result") or str(task.get("result") or ""), **extra)
                if status in self.FAILED:
                    return Outcome(False, error=str(task.get("error") or f"Multica 执行结束：{status}"), result=state.get("result", ""), **extra)
            if time.monotonic() > deadline:
                handle.terminate()
                return Outcome(False, error="Multica 执行超时", external_id=issue)
            handle.wake.wait(self.poll_seconds)

    @staticmethod
    def _message(message: dict[str, Any], state: dict[str, Any]) -> str | None:
        kind = str(message.get("type") or message.get("kind") or "").lower()
        text = message.get("content") or message.get("text") or message.get("output") or ""
        tool = message.get("tool") or message.get("tool_name") or message.get("name")
        if tool and "result" not in kind:
            return _tool_line(str(tool), message.get("input") if isinstance(message.get("input"), dict) else {}, state)
        if kind in ("text", "assistant", "message", "final", "result") and text:
            state["result"] = str(text)
        return _brief(f"↳ {text}" if "result" in kind and tool else text) or None


def _json(text: str) -> Any:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


RUNTIMES: dict[str, Runtime] = {runtime.id: runtime for runtime in (CodexRuntime(), KimiRuntime(), ClaudeRuntime(), MulticaRuntime())}


def execute(runtime: Runtime, executable: str, prompt: str, workspace: Path,
            on_start: Callable[[Any], None], on_log: Callable[[str], None]) -> Outcome:
    """Run one agent turn to completion, streaming log lines; never raises for agent failures."""
    workspace = workspace.resolve()
    state: dict[str, Any] = {"workspace": workspace}
    with tempfile.TemporaryDirectory(prefix="personal-os-run-") as temp:
        output = Path(temp) / "result.txt"
        command = runtime.command(executable, workspace, output, prompt)
        if runtime.sandboxed:
            if not Path(SANDBOX_EXEC).is_file():
                return Outcome(False, error=f"本机缺少 sandbox-exec，无法把 {runtime.label} 限制在工作目录内，已拒绝执行")
            command = [SANDBOX_EXEC, "-p", sandbox_profile(workspace, runtime.state_paths or []), *command]
        try:
            process = subprocess.Popen(command, cwd=str(workspace),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True)
        except OSError as exc:
            return Outcome(False, error=str(exc))
        on_start(process)
        timed_out = threading.Event()

        def expire() -> None:
            timed_out.set()
            stop_process(process, signal.SIGKILL)

        errors: list[str] = []

        def drain() -> None:
            for line in process.stderr:
                errors.append(line)
                del errors[:-200]
                if line.strip():
                    on_log(line.strip())

        timer = threading.Timer(RUN_TIMEOUT, expire)
        timer.daemon = True
        timer.start()
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        lines, size = [], 0
        try:
            try:
                process.stdin.write("" if runtime.prompt_in_argv else prompt)
                process.stdin.close()
            except OSError:
                pass
            for line in process.stdout:
                if size < STDOUT_LIMIT:
                    lines.append(line)
                    size += len(line)
                text = runtime.progress(line, state)
                if text:
                    on_log(text)
            process.wait()
        finally:
            timer.cancel()
        reader.join(5)
        for stream in (process.stdout, process.stderr):
            getattr(stream, "close", lambda: None)()
        extra = {"external_id": str(state.get("external_id") or ""), "outside_writes": state.get("outside_writes")}
        if timed_out.is_set():
            return Outcome(False, error=f"{runtime.label} 执行超时", **extra)
        result = runtime.result(state, "".join(lines), output)
        if process.returncode == 0 and not state.get("error"):
            return Outcome(True, result=result, **extra)
        error = state.get("error") or "".join(errors)[-ERROR_LIMIT:].strip() or f"{runtime.label} 执行失败"
        return Outcome(False, result=result, error=error[-ERROR_LIMIT:], **extra)
