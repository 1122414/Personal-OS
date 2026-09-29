"""Agent runtimes: how each agent CLI is launched and how its output is read.

Personal OS owns tasks, runs and review. A runtime only knows its command line
and output format, so adding or replacing an agent never touches that data.
Every run gets its own process group so cancel and timeout also stop the tools
the agent spawned.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

RUN_TIMEOUT = 3600
STDOUT_LIMIT = 2_000_000
ERROR_LIMIT = 4000


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


class Runtime:
    id = ""
    label = ""
    binary = ""

    @property
    def setting(self) -> str:
        return f"{self.id}_command"

    def command_path(self, settings: dict[str, Any]) -> str | None:
        return resolve_command(settings.get(self.setting) or self.binary)

    def command(self, executable: str, workspace: Path, output: Path) -> list[str]:
        raise NotImplementedError

    def progress(self, line: str, state: dict[str, Any]) -> str | None:
        """Turn one stdout line into a log line; may record result/error/external_id in state."""
        return line.strip() or None

    def result(self, state: dict[str, Any], stdout: str, output: Path) -> str:
        return state.get("result") or stdout


class CodexRuntime(Runtime):
    id, label, binary = "codex", "Codex", "codex"

    def command(self, executable: str, workspace: Path, output: Path) -> list[str]:
        return [executable, "exec", "--ephemeral", "--skip-git-repo-check", "-s", "workspace-write",
                "-C", str(workspace), "-o", str(output), "-"]

    def result(self, state: dict[str, Any], stdout: str, output: Path) -> str:
        return output.read_text(encoding="utf-8") if output.exists() else stdout


RUNTIMES: dict[str, Runtime] = {runtime.id: runtime for runtime in (CodexRuntime(),)}


def execute(runtime: Runtime, executable: str, prompt: str, workspace: Path,
            on_start: Callable[[Any], None], on_log: Callable[[str], None]) -> Outcome:
    """Run one agent turn to completion, streaming log lines; never raises for agent failures."""
    state: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="personal-os-run-") as temp:
        output = Path(temp) / "result.txt"
        try:
            process = subprocess.Popen(runtime.command(executable, workspace, output), cwd=str(workspace),
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
                process.stdin.write(prompt)
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
        external_id = str(state.get("external_id") or "")
        if timed_out.is_set():
            return Outcome(False, error=f"{runtime.label} 执行超时", external_id=external_id)
        result = runtime.result(state, "".join(lines), output)
        if process.returncode == 0 and not state.get("error"):
            return Outcome(True, result=result, external_id=external_id)
        error = state.get("error") or "".join(errors)[-ERROR_LIMIT:].strip() or f"{runtime.label} 执行失败"
        return Outcome(False, result=result, error=error[-ERROR_LIMIT:], external_id=external_id)
