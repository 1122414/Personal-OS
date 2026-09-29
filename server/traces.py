"""Read-only work traces from registered projects and local agent sessions.

Traces are stored as activity events at their source time, so per-day history,
daily-log sources and staleness checks apply to them unchanged. Nothing in this
module writes to a repository, transcript or external database.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .common import local_day, stamp, synchronized

TRACE_KINDS = ("trace_sync",)
TRACE_ACTIONS = ("list_repo_candidates", "register_projects", "sync_traces")
BACKFILL_DAYS = 14
CANDIDATE_DAYS = 30
MAX_COMMITS = 200
MAX_SESSION_FILES = 300
MAX_SESSION_BYTES = 256_000_000
MAX_READ_PER_FILE = 32_000_000
MAX_LINE_BYTES = 2_000_000
TITLE_LIMIT = 120
TEXT_LIMIT = 300
TRACE_TYPES = ("TraceCommit", "TraceSession")
CODEX_NEEDLES = (b'"session_meta"', b'"turn_context"', b'"role"')
CODEX_REQUEST = "## My request for Codex:"
TEMPORARY_WORKSPACES = ("var-folders-", "private-var-", "tmp-", "empty-window")
CURSOR_TIME = re.compile(r"<timestamp>([^<]+?)\s*\(UTC([+-]\d{1,2})(?::?(\d{2}))?\)</timestamp>")


def local_time(value: datetime) -> str:
    if not value.tzinfo:
        value = value.astimezone()
    return value.astimezone().isoformat(timespec="microseconds")


def clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def cursor_key(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-")


def git(path: str, *args: str) -> str:
    result = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError((result.stderr or "git 读取失败").strip()[:200])
    return result.stdout


def read_commits(path: str, since: str, limit: int = MAX_COMMITS) -> list[dict[str, str]]:
    output = git(path, "log", f"--since={since}", "--no-merges", f"--max-count={limit}", "--format=%H%x1f%aI%x1f%s")
    commits = []
    for line in output.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            commits.append({"hash": parts[0], "at": local_time(datetime.fromisoformat(parts[1])), "subject": parts[2]})
    return commits


def texts(content: Any, kinds: tuple[str, ...]) -> list[str]:
    if isinstance(content, str):
        return [content]
    return [part.get("text", "") for part in content or [] if isinstance(part, dict) and part.get("type") in kinds]


def cursor_time(text: str) -> datetime | None:
    match = CURSOR_TIME.search(text)
    if not match:
        return None
    hours, minutes = int(match.group(2)), int(match.group(3) or 0)
    offset = timedelta(hours=hours, minutes=minutes if hours >= 0 else -minutes)
    try:
        return datetime.strptime(match.group(1).strip(), "%A, %b %d, %Y, %I:%M %p").replace(tzinfo=timezone(offset))
    except ValueError:
        return None


def user_query(text: str) -> str:
    match = re.search(r"<user_query>(.*?)</user_query>", text, re.S)
    return (match.group(1) if match else re.sub(r"<[^>]+>[^<]*</[^>]+>", "", text)).strip()


def read_appended(path: Path, offset: int, needles: tuple[bytes, ...] = ()) -> tuple[list[dict[str, Any]], int]:
    """Parse complete JSON lines appended after offset, reading at most one window from the tail."""
    size = path.stat().st_size
    if offset > size:
        offset = 0
    start = max(offset, size - MAX_READ_PER_FILE)
    with path.open("rb") as stream:
        stream.seek(start)
        data = stream.read(size - start)
    skip = 0
    if start > offset:
        skip = data.find(b"\n") + 1
        if not skip:
            return [], start
    end = data.rfind(b"\n") + 1
    if end <= skip:
        return [], start + skip if start > offset else offset
    items = []
    for line in data[skip:end].split(b"\n"):
        if not line or len(line) > MAX_LINE_BYTES or (needles and not any(n in line for n in needles)):
            continue
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(value, dict):
            items.append(value)
    return items, start + end


def first_line(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        line = stream.readline(MAX_LINE_BYTES + 1)
    try:
        value = json.loads(line) if len(line) <= MAX_LINE_BYTES else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def accumulate(entry: dict[str, Any], turns: list[tuple[datetime | None, str, str]], fallback: datetime) -> None:
    """Fold (time, role, text) turns into the entry's per-local-day session slices."""
    days = entry.setdefault("days", {})
    current = datetime.fromisoformat(entry["current"]) if entry.get("current") else None
    for moment, role, text in turns:
        if moment:
            current = moment.astimezone()
        at = current or fallback
        slot = days.setdefault(at.date().isoformat(), {"title": "", "last_text": "", "at": local_time(at)})
        slot["at"] = max(slot["at"], local_time(at))
        if role == "user" and not slot["title"] and text:
            slot["title"] = clip(text, TITLE_LIMIT)
        if role == "assistant" and text:
            slot["last_text"] = clip(text, TEXT_LIMIT)
    entry["current"] = local_time(current) if current else None


def read_cursor(path: Path, entry: dict[str, Any]) -> None:
    items, entry["offset"] = read_appended(path, entry.get("offset", 0))
    turns = []
    for item in items:
        role, message = item.get("role"), item.get("message") or {}
        content = texts(message.get("content"), ("text",))
        if role == "user":
            raw = "\n".join(content)
            turns.append((cursor_time(raw), "user", user_query(raw)))
        elif role == "assistant":
            text = "\n".join(t for t in content if t.strip())
            if text:
                turns.append((None, "assistant", text))
    accumulate(entry, turns, datetime.fromtimestamp(path.stat().st_mtime).astimezone())


def read_codex(path: Path, entry: dict[str, Any]) -> None:
    if "subagent" not in entry:
        meta = first_line(path)
        payload = (meta.get("payload") or {}) if meta.get("type") == "session_meta" else {}
        entry["cwd"] = entry.get("cwd") or payload.get("cwd") or ""
        entry["subagent"] = bool(payload.get("parent_thread_id"))
    items, entry["offset"] = read_appended(path, entry.get("offset", 0), CODEX_NEEDLES)
    turns = []
    for item in items:
        payload = item.get("payload") or {}
        try:
            moment = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError, AttributeError):
            moment = None
        if item.get("type") in ("session_meta", "turn_context") and not entry.get("cwd"):
            entry["cwd"] = payload.get("cwd") or ""
        elif item.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") in ("user", "assistant"):
            kinds = ("input_text",) if payload["role"] == "user" else ("output_text",)
            text = "\n".join(codex_text(t) for t in texts(payload.get("content"), kinds))
            if text.strip():
                turns.append((moment, payload["role"], text))
    accumulate(entry, turns, datetime.fromtimestamp(path.stat().st_mtime).astimezone())


def codex_text(text: str) -> str:
    """Drop context Codex injects into user turns; keep what the person actually typed."""
    if CODEX_REQUEST in text:
        text = text.split(CODEX_REQUEST, 1)[1]
    stripped = text.lstrip()
    if stripped.startswith(("<", "# AGENTS.md")) or "<INSTRUCTIONS>" in text:
        return ""
    return text


class TracesMixin:
    cursor_projects = Path.home() / ".cursor" / "projects"
    codex_sessions_root = Path.home() / ".codex" / "sessions"

    def _trace_state(self) -> dict[str, Any]:
        return self.get("trace_sync", "trace_sync") or {"id": "trace_sync", "files": {}}

    def _trace_projects(self) -> list[dict[str, Any]]:
        return [p for p in self.all("project") if p.get("status") == "Active" and p.get("workspace_path") and Path(p["workspace_path"]).is_dir()]

    @staticmethod
    def _match_project(projects: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
        if not path:
            return None
        matches = [p for p in projects if path == p["workspace_path"].rstrip("/") or path.startswith(p["workspace_path"].rstrip("/") + "/")]
        return max(matches, key=lambda p: len(p["workspace_path"]), default=None)

    @synchronized
    def record_trace(self, event_type: str, key: str, at: str, project_id: str | None, details: dict[str, Any]) -> None:
        trace_id = "trace-" + hashlib.sha256(key.encode()).hexdigest()[:32]
        self.db.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "project_id=excluded.project_id, details=excluded.details, created_at=excluded.created_at",
            (trace_id, event_type, "project" if project_id else None, project_id, project_id,
             json.dumps(details, ensure_ascii=False), at),
        )
        self.db.commit()

    def list_repo_candidates(self, p: dict[str, Any]) -> dict[str, Any]:
        root = Path(self.get("settings", "settings").get("repo_scan_root") or "~/My-Item").expanduser()
        if not root.is_dir():
            return {"root": str(root), "candidates": [], "message": "扫描目录不存在，请在设置中修改"}
        registered = {str(Path(x["workspace_path"]).resolve()) for x in self.all("project") if x.get("workspace_path")}
        since = (date.today() - timedelta(days=CANDIDATE_DAYS)).isoformat()
        candidates = []
        for path in sorted(root.iterdir()):
            if path.is_symlink() or not (path / ".git").exists() or str(path.resolve()) in registered:
                continue
            try:
                commits = read_commits(str(path), since, 500)
            except (ValueError, OSError, subprocess.SubprocessError):
                continue
            if commits:
                candidates.append({"name": path.name, "path": str(path.resolve()), "commits": len(commits), "last_commit_at": commits[0]["at"]})
        candidates.sort(key=lambda x: x["last_commit_at"], reverse=True)
        return {"root": str(root), "candidates": candidates}

    def register_projects(self, p: dict[str, Any]) -> dict[str, Any]:
        paths = p.get("paths")
        if not isinstance(paths, list) or not paths or len(paths) > 50:
            raise ValueError("请选择要登记的仓库")
        registered = {str(Path(x["workspace_path"]).resolve()) for x in self.all("project") if x.get("workspace_path")}
        created = []
        for value in paths:
            if not isinstance(value, str):
                raise ValueError("仓库路径无效")
            path = Path(value).expanduser().resolve()
            if not (path / ".git").exists():
                raise ValueError(f"{path} 不是 git 仓库")
            if str(path) in registered:
                continue
            created.append(self.create_project({"name": path.name, "workspace_path": str(path), "stage": "进行中"}))
            registered.add(str(path))
        synced = self.sync_traces({"force": True})
        return {"projects": created, "sync": synced, "message": f"已登记 {len(created)} 个项目，{synced['message']}"}

    def sync_traces(self, p: dict[str, Any]) -> dict[str, Any]:
        if not self._trace_lock.acquire(blocking=False):
            raise ValueError("工作痕迹正在同步，请稍候")
        try:
            return self._sync_traces(bool(p.get("force")))
        finally:
            self._trace_lock.release()

    def _sync_traces(self, force: bool) -> dict[str, Any]:
        projects = self._trace_projects()
        since_day = date.today() - timedelta(days=BACKFILL_DAYS)
        state = self._trace_state()
        errors, counts = [], {"commits": 0, "sessions": 0}

        for project in projects:
            try:
                for commit in read_commits(project["workspace_path"], since_day.isoformat()):
                    self.record_trace("TraceCommit", f"git:{project['workspace_path']}:{commit['hash']}", commit["at"], project["id"],
                                      {"source": "git", "title": clip(commit["subject"], TITLE_LIMIT), "ref": commit["hash"], "project": project["name"]})
                    counts["commits"] += 1
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                errors.append({"source": project["name"], "error": str(exc)[:200]})

        cutoff = datetime.combine(since_day, datetime.min.time()).timestamp()
        files = []
        cursor_root = Path(self.cursor_projects)
        if cursor_root.is_dir():
            for folder in cursor_root.iterdir():
                transcripts = folder / "agent-transcripts"
                if transcripts.is_dir() and not folder.is_symlink():
                    files.extend(("cursor", folder.name, path) for path in transcripts.glob("*/*.jsonl"))
        codex_root = Path(self.codex_sessions_root)
        if codex_root.is_dir():
            files.extend(("codex", "", path) for path in codex_root.rglob("*.jsonl"))
        recent = []
        for source, folder, path in files:
            try:
                info = path.stat()
            except OSError:
                continue
            if not path.is_symlink() and info.st_mtime >= cutoff:
                recent.append((info.st_mtime, info.st_size, source, folder, path))
        recent.sort(reverse=True)
        by_key = {cursor_key(x["workspace_path"]): x for x in projects}
        recent = [x for x in recent if not (x[2] == "cursor" and x[3] not in by_key and x[3].startswith(TEMPORARY_WORKSPACES))]
        known, files_state, consumed, over_budget = state.get("files", {}), {}, 0, False
        for mtime, size, source, folder, path in recent[:MAX_SESSION_FILES]:
            key = str(path)
            entry = known.get(key) or {"offset": 0, "days": {}, "cwd": "", "current": None}
            signature = f"{size}:{mtime}"
            changed = entry.get("sig") != signature
            if changed:
                offset = entry.get("offset", 0)
                pending = min(size - offset if size >= offset else size, MAX_READ_PER_FILE)
                if consumed + pending > MAX_SESSION_BYTES:
                    over_budget = True
                    if key in known:
                        files_state[key] = entry
                    continue
                consumed += pending
                try:
                    (read_cursor if source == "cursor" else read_codex)(path, entry)
                except OSError as exc:
                    errors.append({"source": source, "error": f"{path.name}：{exc}"[:200]})
                    continue
                entry["sig"] = signature
                entry["days"] = {day: value for day, value in entry["days"].items() if day >= since_day.isoformat()}
            files_state[key] = entry
            if not (changed or force) or entry.get("subagent"):
                continue
            project = by_key.get(folder) if source == "cursor" else self._match_project(projects, entry.get("cwd", ""))
            label = "Cursor" if source == "cursor" else "Codex"
            for day, item in entry["days"].items():
                if not (item["title"] or item["last_text"]):
                    continue
                self.record_trace("TraceSession", f"{source}:{path}:{day}", item["at"], project["id"] if project else None, {
                    "source": source, "label": label, "title": item["title"] or f"{label} 会话", "last_text": item["last_text"],
                    "ref": key, "workspace": entry.get("cwd") or (project or {}).get("workspace_path", ""), "project": project["name"] if project else "",
                })
                counts["sessions"] += 1
        if over_budget:
            errors.append({"source": "会话", "error": "本次会话读取量达到上限，其余内容下次同步继续"})

        root = self.get("settings", "settings").get("workbuddy_root")
        if root:
            try:
                counts["sessions"] += self._sync_workbuddy_traces(Path(root), projects, cutoff)
            except (ValueError, OSError, sqlite3.DatabaseError) as exc:
                errors.append({"source": "WorkBuddy", "error": str(exc)[:200]})

        with self.lock:
            if getattr(self, "_stopping", False):
                raise ValueError("服务正在关闭，同步未完成")
            state = self._trace_state()
            state.update(files=files_state, last_sync_at=stamp(), errors=errors[:20], error_count=len(errors))
            self.put("trace_sync", state)
        message = f"读取 {counts['commits']} 条提交、{counts['sessions']} 段会话" + (f"，{len(errors)} 个来源失败" if errors else "")
        return {**counts, "errors": errors[:20], "message": message}

    def _sync_workbuddy_traces(self, root: Path, projects: list[dict[str, Any]], cutoff: float) -> int:
        database = root / "workbuddy.db"
        if not database.is_file() or database.is_symlink():
            raise ValueError("WorkBuddy 数据库不可读取")
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            if not {"id", "title", "cwd", "updated_at", "deleted_at"}.issubset(columns):
                raise ValueError("WorkBuddy 会话格式已变化，跳过")
            rows = db.execute("SELECT id,title,cwd,updated_at FROM sessions WHERE deleted_at IS NULL AND updated_at>=? ORDER BY updated_at DESC LIMIT 500",
                              (int(cutoff * 1000),)).fetchall()
        count = 0
        for sid, title, cwd, updated in rows:
            at = datetime.fromtimestamp(updated / 1000).astimezone()
            project = self._match_project(projects, cwd or "")
            self.record_trace("TraceSession", f"workbuddy:{sid}", local_time(at), project["id"] if project else None, {
                "source": "workbuddy", "label": "WorkBuddy", "title": clip(title or "WorkBuddy 会话", TITLE_LIMIT), "last_text": "",
                "ref": str(sid), "workspace": cwd or "", "project": project["name"] if project else "",
            })
            count += 1
        return count

    @synchronized
    def last_work(self) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT max(substr(created_at,1,10)) FROM activity WHERE substr(created_at,1,10) < ? AND "
            "(type LIKE 'Trace%' OR type LIKE 'Task%' OR type LIKE 'Agent%')", (local_day(),),
        ).fetchone()
        day = row[0] if row else None
        if not day:
            return None
        projects = {p["id"]: p for p in self.all("project")}
        groups: dict[str, dict[str, Any]] = {}
        unassigned = []
        for event in reversed(self.events(day)):
            kind, details = event["type"], event["details"]
            if kind not in (*TRACE_TYPES, "TaskCompleted"):
                continue
            entry = {"id": event["id"], "at": event["created_at"], **details}
            project_id = event.get("project_id")
            if kind == "TraceSession" and not project_id:
                unassigned.append(entry)
                continue
            if not project_id and kind == "TaskCompleted":
                task = self.get("task", event.get("subject_id") or "")
                project_id = task.get("project_id") if task else None
            key = project_id or "none"
            group = groups.setdefault(key, {"project_id": project_id, "name": projects.get(project_id, {}).get("name", "未关联项目"), "commits": [], "sessions": [], "tasks": []})
            group["commits" if kind == "TraceCommit" else "sessions" if kind == "TraceSession" else "tasks"].append(entry)
        ordered = sorted(groups.values(), key=lambda g: max([x["at"] for x in g["commits"] + g["sessions"] + g["tasks"]] or [""]), reverse=True)
        return {"date": day, "groups": ordered, "unassigned_sessions": unassigned}
