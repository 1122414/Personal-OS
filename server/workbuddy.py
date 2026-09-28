"""Read-only adapter for the locally verified WorkBuddy 5.6 session format.

This is a local-format adapter, not an implementation of WorkBuddy Open API.
Only session metadata and user/assistant message text are read.
"""

from contextlib import closing
from datetime import date, datetime, time
import hashlib
import json
from pathlib import Path
import re
import sqlite3


MAX_FILE_BYTES = 32_000_000
MAX_SYNC_BYTES = 64_000_000
MAX_LINE_BYTES = 2_000_000


def source_root(value: str) -> Path:
    root = Path(value).expanduser().resolve()
    database = root / "workbuddy.db"
    if not database.is_file() or database.is_symlink():
        raise ValueError("该目录没有可读取的 WorkBuddy 数据库 workbuddy.db")
    return root


def iso_time(milliseconds: int) -> str:
    return datetime.fromtimestamp(milliseconds / 1000).astimezone().isoformat()


def message_text(path: Path) -> tuple[str, str, bool]:
    """Bounded visible transcript; deliberately ignore tool calls and reasoning."""
    messages, last_answer = [], ""
    incomplete = False
    with path.open("rb") as stream:
        while True:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                incomplete = True
                while line and not line.endswith(b"\n"):
                    line = stream.readline(MAX_LINE_BYTES + 1)
                continue
            try:
                item = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                incomplete = True
                continue
            if not isinstance(item, dict) or item.get("type") != "message" or item.get("role") not in ("user", "assistant"):
                continue
            blocks = item.get("content", [])
            if not isinstance(blocks, list):
                incomplete = True
                continue
            text = "\n".join(block["text"] for block in blocks if isinstance(block, dict) and block.get("type") in ("text", "input_text", "output_text") and isinstance(block.get("text"), str)).strip()
            if not text:
                continue
            if len(text) > 20000:
                incomplete = True
            text = text[:20000]
            messages.append(("用户" if item["role"] == "user" else "WorkBuddy") + "：\n" + text)
            if len(messages) > 20:
                messages.pop(0)
                incomplete = True
            if item["role"] == "assistant":
                last_answer = text
    transcript = "\n\n".join(messages)
    incomplete = incomplete or len(transcript) > 30000
    return transcript[-30000:], last_answer[:5000], incomplete


def read_updates(value: str, since: str, known: dict[str, str]) -> dict:
    root = source_root(value)
    try:
        cutoff = int(datetime.combine(date.fromisoformat(since), time.min).timestamp() * 1000)
    except (ValueError, TypeError):
        raise ValueError("WorkBuddy 起始日期无效") from None
    required = {"id", "title", "status", "created_at", "updated_at", "deleted_at", "cwd"}
    try:
        with closing(sqlite3.connect((root / "workbuddy.db").as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
            db.row_factory = sqlite3.Row
            columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            if not required.issubset(columns):
                raise ValueError("WorkBuddy 会话格式已变化，停止同步以保护现有数据")
            title = "COALESCE(NULLIF(custom_title,''),title)" if "custom_title" in columns else "title"
            rows = [dict(row) for row in db.execute(
                f"SELECT id,{title} AS title,status,cwd,created_at,updated_at FROM sessions WHERE deleted_at IS NULL AND updated_at>=? ORDER BY updated_at DESC,id LIMIT 1001", (cutoff,))]
    except sqlite3.DatabaseError as exc:
        raise ValueError("WorkBuddy 数据库暂不可读取或版本不兼容") from exc
    paths = {}
    project_root = root / "projects"
    if project_root.is_symlink() or not project_root.resolve().is_relative_to(root):
        raise ValueError("WorkBuddy 正文目录不能链接到数据目录之外")
    for path in project_root.glob("*/*.jsonl"):
        if path.is_symlink() or not path.resolve().is_relative_to(project_root.resolve()):
            continue
        if path.stem in paths:
            paths[path.stem] = None  # Ambiguous IDs must not silently pick one transcript.
        else:
            paths[path.stem] = path
    records, errors, consumed = [], [], 0
    if len(rows) > 1000:
        errors.append({"source": "WorkBuddy", "error": "本次只检查最近 1000 个会话，请缩短日期范围；更早记录未导入"})
    unchanged = 0
    for row in rows[:1000]:
        sid = row["id"]
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", sid):
            errors.append({"source": "WorkBuddy", "error": "跳过无效会话标识"})
            continue
        path = paths.get(sid)
        if path is None:
            errors.append({"source": sid, "error": "本地正文不存在或存在重复标识，暂未导入"})
            continue
        try:
            stat = path.stat()
            signature = hashlib.sha256(json.dumps([row, stat.st_size, stat.st_mtime_ns], sort_keys=True).encode()).hexdigest()
            if known.get(sid) == signature:
                unchanged += 1
                continue
            if stat.st_size > MAX_FILE_BYTES or consumed + stat.st_size > MAX_SYNC_BYTES:
                errors.append({"source": sid, "error": "正文超出本次读取上限，未导入；其他会话可继续同步"})
                continue
            consumed += stat.st_size
            content, summary, incomplete = message_text(path)
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                errors.append({"source": sid, "error": "会话正在写入，将在下一次同步重试"})
                continue
            if not content:
                errors.append({"source": sid, "error": "尚无可识别的消息正文，未导入"})
                continue
            records.append({"external_id": sid, "title": (row["title"] or "WorkBuddy 会话")[:300],
                            "content": content, "summary": summary or "仅有用户输入，尚无最终回复。",
                            "source_status": row["status"], "source_workspace": row["cwd"],
                            "source_updated_at": iso_time(row["updated_at"]), "published_at": iso_time(row["created_at"]),
                            "source_path": str(path), "source_fingerprint": signature, "content_incomplete": incomplete})
        except (OSError, ValueError, TypeError, OverflowError) as exc:
            errors.append({"source": sid, "error": "会话暂不可读取或格式不兼容"})
    return {"records": records, "errors": errors, "unchanged": unchanged, "checked": min(len(rows), 1000)}
