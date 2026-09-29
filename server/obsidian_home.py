"""Long-running items from the Obsidian notes homepage.

Obsidian stays the source of truth: the item list comes from `首页数据/工作台.json`
and progress lives in each linked note's frontmatter. Writes touch exactly one
`home_*` line and refuse to overwrite a note that changed since it was read.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

HOME_ACTIONS = ("update_home_item",)
HOME_CONFIG = Path("首页数据") / "工作台.json"
HOME_FIELDS = ("home_progress", "home_next", "home_status")
HOME_STATUSES = ("active", "paused", "done")
MAX_NOTE_BYTES = 1_000_000
MAX_VALUE = 500


def vault_path(settings: dict[str, Any]) -> Path:
    value = settings.get("obsidian_vault")
    if not value or not Path(value).is_dir():
        raise ValueError("尚未配置 Obsidian vault")
    return Path(value).resolve()


def note_path(vault: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative.endswith(".md"):
        raise ValueError("关联笔记路径无效")
    parts = Path(relative).parts
    if Path(relative).is_absolute() or any(part in ("..", ".") or part.startswith(".") for part in parts):
        raise ValueError("关联笔记必须位于 vault 内")
    path = vault
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("关联笔记不能经过符号链接")
    if not path.resolve().is_relative_to(vault):
        raise ValueError("关联笔记必须位于 vault 内")
    return path


def version(path: Path) -> str:
    info = path.stat()
    return f"{info.st_mtime_ns}:{info.st_size}"


def split_frontmatter(text: str) -> tuple[list[str] | None, str]:
    """Return (frontmatter lines, body) when the note starts with a `---` block."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        if text.endswith("\n---"):
            end = len(text) - 4
        else:
            return None, text
    return text[4:end].split("\n") if end > 4 else [], text[end + 5:]


def scalar(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
            return value if isinstance(value, str) else str(value)
        except json.JSONDecodeError:
            return raw.strip('"')
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    return raw


def read_fields(lines: list[str] | None) -> dict[str, str]:
    values = {}
    for line in lines or []:
        key, sep, raw = line.partition(":")
        if sep and key in HOME_FIELDS and not line.startswith((" ", "\t")):
            values[key] = scalar(raw)
    return values


def patch_field(text: str, field: str, value: str) -> str:
    lines, body = split_frontmatter(text)
    entry = f"{field}: {json.dumps(value, ensure_ascii=False)}"
    if lines is None:
        return f"---\n{entry}\n---\n{text}"
    index = next((i for i, line in enumerate(lines) if line.partition(":")[0] == field and line.partition(":")[1]), None)
    if index is None:
        lines.append(entry)
    else:
        end = index + 1
        while end < len(lines) and lines[end].startswith((" ", "\t")):
            end += 1
        lines[index:end] = [entry]
    return "---\n" + "\n".join(lines) + "\n---\n" + body


class ObsidianHomeMixin:
    def home_items(self) -> dict[str, Any]:
        result = {"configured": False, "items": [], "errors": []}
        try:
            vault = vault_path(self.get("settings", "settings"))
            config = vault / HOME_CONFIG
            if not config.is_file() or config.is_symlink():
                result["errors"].append("没有找到 Obsidian 首页配置（首页数据/工作台.json）")
                return result
            tasks = json.loads(config.read_text(encoding="utf-8")).get("tasks", [])
            result["configured"] = True
        except ValueError as exc:
            result["errors"].append(str(exc))
            return result
        except (OSError, json.JSONDecodeError, AttributeError):
            result["errors"].append("Obsidian 首页配置无法读取")
            return result
        for task in tasks if isinstance(tasks, list) else []:
            if not isinstance(task, dict):
                continue
            item = {"id": str(task.get("id") or task.get("note")), "title": str(task.get("title") or "未命名事项"),
                    "subtitle": str(task.get("subtitle") or ""), "note": task.get("note"),
                    "home_progress": "", "home_next": "", "home_status": "active", "version": None, "error": None}
            try:
                path = note_path(vault, task.get("note"))
                if not path.is_file():
                    raise ValueError("关联笔记不存在，请在 Obsidian 首页重新关联")
                if path.stat().st_size > MAX_NOTE_BYTES:
                    raise ValueError("关联笔记过大，暂不读取")
                item["version"] = version(path)
                fields = read_fields(split_frontmatter(path.read_text(encoding="utf-8"))[0])
                item.update({k: v for k, v in fields.items() if v or k != "home_status"})
                if item["home_status"] not in HOME_STATUSES:
                    item["home_status"] = "active"
            except (ValueError, OSError, UnicodeDecodeError) as exc:
                item["error"] = str(exc) if isinstance(exc, ValueError) else "关联笔记暂不可读取"
            result["items"].append(item)
        return result

    def update_home_item(self, p: dict[str, Any]) -> dict[str, Any]:
        field, value = p.get("field"), p.get("value")
        if field not in HOME_FIELDS:
            raise ValueError("只能修改进度、下一步或状态")
        if not isinstance(value, str) or len(value) > MAX_VALUE:
            raise ValueError("内容格式无效或过长")
        value = " ".join(value.split())
        if field == "home_status" and value not in HOME_STATUSES:
            raise ValueError("状态无效")
        vault = vault_path(self.get("settings", "settings"))
        path = note_path(vault, p.get("note"))
        if not path.is_file():
            raise ValueError("关联笔记不存在")
        if version(path) != p.get("expected_version"):
            raise ValueError("笔记已在别处修改，请刷新后再改")
        text = path.read_text(encoding="utf-8")
        updated = patch_field(text, field, value)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".personal-os-", suffix=".md")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(updated)
            shutil.copymode(path, temporary)
            if version(path) != p["expected_version"]:
                raise ValueError("笔记已在别处修改，请刷新后再改")
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.event("HomeItemUpdated", details={"title": p.get("title") or path.stem, "note": p["note"], "field": field})
        return {"note": p["note"], "field": field, "value": value, "version": version(path)}
