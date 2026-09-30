"""Local HTTP API and production static file server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import signal
import sqlite3
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .store import Store, local_day, stamp
from .reports import read_report
from .workspace import MAX_ATTACHMENT_BYTES


ROOT = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 1_000_000
TRACE_SYNC_SECONDS = 600


def is_local_origin(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return (parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "localhost")
                and parsed.port != 0
                and not (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment))
    except ValueError:
        # Malformed brackets and ports must fail closed, not abort the handler.
        return False


def migrate_legacy_database(source: Path, target: Path) -> bool:
    """Copy the web MVP database once, using SQLite backup even if it is open."""
    if target.exists() or not source.is_file() or source.resolve() == target.resolve():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="personal-os-migrate-", suffix=".sqlite3", dir=target.parent, delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        with sqlite3.connect(source) as old, sqlite3.connect(pending) as new:
            old.backup(new)
        try:
            os.link(pending, target)
        except FileExistsError:
            return False
    finally:
        pending.unlink(missing_ok=True)
    return True


def make_handler(store: Store, static_root: Path):
    class Handler(BaseHTTPRequestHandler):
        def _local_request(self, mutation: bool = False) -> bool:
            if not is_local_origin("http://" + self.headers.get("Host", "")):
                return False
            if mutation:
                origin = self.headers.get("Origin")
                if origin and not is_local_origin(origin):
                    return False
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                    return False
            return True

        def _json(self, status: int, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if not self._local_request():
                self._json(403, {"error": "仅允许本机访问"})
                return
            route = urlparse(self.path).path
            if route == "/api/state":
                self._json(200, store.state())
                return
            if route.startswith("/api/learning/"):
                try:
                    self._json(200, store.learning_detail(route.removeprefix("/api/learning/")))
                except ValueError as exc:
                    self._json(404, {"error": str(exc)})
                return
            if route == "/api/agent_runs/running":
                self._json(200, {"agent_runs": store.running_agent_runs()})
                return
            if route == "/api/health":
                self._json(200, {"status": "ok"})
                return
            if route.startswith("/api/material/"):
                try:
                    material, body = store.material_original(route.removeprefix("/api/material/"))
                    self.send_response(200)
                    self.send_header("Content-Type", material["mime"])
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Content-Disposition", f'inline; filename="{material["id"]}{material["extension"]}"')
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                except ValueError as exc:
                    self._json(404, {"error": str(exc)})
                return
            if route == "/api/obsidian/report":
                try:
                    query = parse_qs(urlparse(self.path).query)
                    self._json(200, read_report(store.get("settings", "settings"), query.get("path", [""])[0], query.get("module", [None])[0]))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            if route == "/api/agent_models":
                try:
                    self._json(200, store.agent_models(parse_qs(urlparse(self.path).query).get("runtime", [""])[0]))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            if route == "/api/history":
                try:
                    day = parse_qs(urlparse(self.path).query).get("date", [local_day()])[0]
                    self._json(200, store.history(day))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            if route == "/api/obsidian/recent":
                settings = store.get("settings", "settings") or {}
                vault_path = settings.get("obsidian_vault") or ""
                if not vault_path:
                    self._json(200, {"configured": False, "files": []})
                    return
                vault = Path(vault_path)
                if not vault.is_dir():
                    self._json(200, {"configured": False, "files": []})
                    return
                files = []
                try:
                    for path in vault.rglob("*.md"):
                        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(vault).parts):
                            stat = path.stat()
                            files.append({"path": str(path.relative_to(vault)), "modified_at": stat.st_mtime})
                    files.sort(key=lambda item: item["modified_at"], reverse=True)
                    self._json(200, {"configured": True, "files": files[:20]})
                except OSError as exc:
                    self._json(500, {"error": str(exc)})
                return
            if route.startswith("/api/"):
                self._json(404, {"error": "未找到接口"})
                return
            relative = unquote(route).lstrip("/") or "index.html"
            target = (static_root / relative).resolve()
            if not target.is_relative_to(static_root.resolve()):
                self._json(403, {"error": "无权访问"})
                return
            if not target.is_file():
                target = static_root / "index.html"
            if not target.is_file():
                self._json(404, {"error": "前端尚未构建，请运行 npm run dev"})
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if not self._local_request(mutation=True):
                self._json(403, {"error": "仅允许本机 JSON 请求"})
                return
            route = urlparse(self.path).path
            if not route.startswith("/api/action/"):
                self._json(404, {"error": "未找到接口"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                limit = MAX_ATTACHMENT_BYTES * 4 // 3 + 10000 if route == "/api/action/add_material" else MAX_BODY_BYTES
                if length < 0 or length > limit:
                    raise ValueError("请求内容过大")
                data = json.loads(self.rfile.read(length))
                result = store.action(route.removeprefix("/api/action/"), data)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, {"result": result, "state": store.state()})

    return Handler


def daily_automation(store: Store, stop: threading.Event) -> None:
    """Refresh configured context in the morning and draft the log in the evening."""
    while not stop.is_set():
        try:
            hour = datetime.now().hour
            day = local_day()
            events = store.events(day)
            settings = store.get("settings", "settings")
            last_sync = settings.get("workbuddy_last_sync", {}).get("at")
            due = not last_sync or datetime.now().astimezone().timestamp() - datetime.fromisoformat(last_sync).timestamp() >= 300
            if settings.get("workbuddy_enabled") and due:
                try:
                    store.action("sync_workbuddy", {})
                except (ValueError, OSError) as exc:
                    with store.lock:
                        if not store._stopping:
                            settings = store.get("settings", "settings")
                            settings["workbuddy_last_sync"] = {"at": stamp(), "errors": [{"source": "WorkBuddy", "error": str(exc)}], "error_count": 1}
                            store.put("settings", settings)
            if 8 <= hour < 20:
                refreshed = {event["subject_id"] for event in events if event["type"] == "IntelligenceChannelRefreshed"}
                for channel in store.all("intelligence_channel"):
                    if channel["id"] not in refreshed and channel.get("sources"):
                        store.action("refresh_channel", {"id": channel["id"]})
                pulse_attempts = {event["subject_id"] for event in store.events(day) if event["type"] in ("ProjectPulseGenerated", "ProjectPulseFailed")}
                for project in store.all("project"):
                    has_tasks = any(task.get("project_id") == project["id"] for task in store.all("task"))
                    if project["status"] == "Active" and has_tasks and store.pulse_stale(project) and not project.get("pulse_manual") and project["id"] not in pulse_attempts:
                        try:
                            store.action("generate_project_pulse", {"id": project["id"]})
                        except ValueError as exc:
                            store.event("ProjectPulseFailed", "project", project["id"], project["id"], {"error": str(exc)[:200]})
                store.daily_card_push()
            if hour >= 20 and not any(log["date"] == day for log in store.all("daily_log")):
                store.action("draft_log", {})
        except (OSError, ValueError) as exc:
            print(f"Daily automation: {exc}", flush=True)
        stop.wait(60)


def workspace_automation(store: Store, stop: threading.Event) -> None:
    """Keep short workspace jobs independent from slower RSS/daily generation."""
    last_trace_sync = None
    while not stop.is_set():
        try:
            store.summary_tick()
            store.recall_tick()
        except (ValueError, OSError):
            pass
        if last_trace_sync is None or time.monotonic() - last_trace_sync >= TRACE_SYNC_SECONDS:
            last_trace_sync = time.monotonic()
            try:
                store.action("sync_traces", {})
            except (ValueError, OSError) as exc:
                print(f"Trace sync: {exc}", flush=True)
        stop.wait(10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=os.environ.get("PERSONAL_OS_DB", str(ROOT / "data" / "personal-os.sqlite3")))
    parser.add_argument("--ready-file", default="")
    parser.add_argument("--migrate-from", default="")
    args = parser.parse_args()
    if args.migrate_from:
        migrate_legacy_database(Path(args.migrate_from), Path(args.db))
    store = Store(args.db)
    vault = os.environ.get("PERSONAL_OS_OBSIDIAN_VAULT", "")
    if vault and not store.get("settings", "settings").get("obsidian_vault"):
        store.action("save_settings", {"obsidian_vault": vault})
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, ROOT / "dist"))
    port = server.server_address[1]
    ready_file = Path(args.ready_file) if args.ready_file else None
    if ready_file:
        ready_file.write_text(str(port), encoding="ascii")
    stop = threading.Event()
    if os.environ.get("PERSONAL_OS_DISABLE_AUTOMATION") != "1":
        worker = threading.Thread(target=daily_automation, args=(store, stop), daemon=True)
        worker.start()
        threading.Thread(target=workspace_automation, args=(store, stop), daemon=True).start()
    def request_shutdown(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, request_shutdown)
    print(f"Personal OS API running on http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        store.close()
        if ready_file:
            ready_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
