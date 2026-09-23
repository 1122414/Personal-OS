"""Local HTTP API and production static file server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .store import Store, local_day


ROOT = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 1_000_000


def make_handler(store: Store, static_root: Path):
    class Handler(BaseHTTPRequestHandler):
        def _local_request(self, mutation: bool = False) -> bool:
            host = urlparse("http://" + self.headers.get("Host", "")).hostname
            if host not in ("127.0.0.1", "localhost"):
                return False
            if mutation:
                origin = self.headers.get("Origin")
                if origin:
                    parsed = urlparse(origin)
                    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
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
            if route == "/api/health":
                self._json(200, {"status": "ok"})
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
                if length < 0 or length > MAX_BODY_BYTES:
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
            if 8 <= hour < 20:
                refreshed = {event["subject_id"] for event in events if event["type"] == "IntelligenceChannelRefreshed"}
                for channel in store.all("intelligence_channel"):
                    if channel["id"] not in refreshed and channel.get("sources"):
                        store.action("refresh_channel", {"id": channel["id"]})
                attempted = any(event["type"] in ("MorningBriefGenerated", "MorningBriefFailed") for event in store.events(day))
                pending = any(task["status"] not in ("Done", "Blocked") for task in store.all("task"))
                if pending and not attempted and not any(brief["date"] == day for brief in store.all("daily_brief")):
                    try:
                        store.action("generate_brief", {})
                    except ValueError as exc:
                        store.event("MorningBriefFailed", details={"error": str(exc)[:200]})
                pulse_attempts = {event["subject_id"] for event in store.events(day) if event["type"] in ("ProjectPulseGenerated", "ProjectPulseFailed")}
                for project in store.all("project"):
                    has_tasks = any(task.get("project_id") == project["id"] for task in store.all("task"))
                    if project["status"] == "Active" and has_tasks and not project.get("pulse") and project["id"] not in pulse_attempts:
                        try:
                            store.action("generate_project_pulse", {"id": project["id"]})
                        except ValueError as exc:
                            store.event("ProjectPulseFailed", "project", project["id"], project["id"], {"error": str(exc)[:200]})
            if hour >= 20 and not any(log["date"] == day for log in store.all("daily_log")):
                store.action("draft_log", {})
        except (OSError, ValueError) as exc:
            print(f"Daily automation: {exc}", flush=True)
        stop.wait(60)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default=os.environ.get("PERSONAL_OS_DB", str(ROOT / "data" / "personal-os.sqlite3")))
    args = parser.parse_args()
    store = Store(args.db)
    vault = os.environ.get("PERSONAL_OS_OBSIDIAN_VAULT", "")
    if vault and not store.get("settings", "settings").get("obsidian_vault"):
        store.action("save_settings", {"obsidian_vault": vault})
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(store, ROOT / "dist"))
    stop = threading.Event()
    if os.environ.get("PERSONAL_OS_DISABLE_AUTOMATION") != "1":
        worker = threading.Thread(target=daily_automation, args=(store, stop), daemon=True)
        worker.start()
    print(f"Personal OS API running on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
