"""Local HTTP API and production static file server."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .store import Store


ROOT = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 1_000_000


def make_handler(store: Store, static_root: Path):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
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
    print(f"Personal OS API running on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
