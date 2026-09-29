"""Popen stand-in for agent runs: subclasses override `behave(prompt)`."""

from __future__ import annotations

import threading


class _Stdin:
    def __init__(self):
        self.parts: list[str] = []

    def write(self, text: str) -> int:
        self.parts.append(text)
        return len(text)

    def close(self) -> None:
        pass


class FakeAgentProcess:
    def __init__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        self.stdin = _Stdin()
        self.returncode = None
        self.stopped = threading.Event()
        self._done = threading.Event()
        self._errors: list[str] = []
        self.stdout = self._stdout()
        self.stderr = self._stderr()

    def behave(self, prompt: str) -> tuple[str, str, int]:
        """Return (stdout, stderr, returncode); may block on self.stopped."""
        return "", "", 0

    def _stdout(self):
        out, err, code = self.behave("".join(self.stdin.parts))
        self._errors.extend(err.splitlines(True))
        self.returncode = code
        self._done.set()
        yield from out.splitlines(True)

    def _stderr(self):
        self._done.wait(10)
        yield from self._errors

    def wait(self, timeout=None):
        self._done.wait(timeout)
        return self.returncode

    def poll(self):
        return self.returncode if self._done.is_set() else None

    def terminate(self):
        self.stopped.set()

    def kill(self):
        self.stopped.set()
