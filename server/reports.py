"""Read AI report artifacts directly from a bounded directory inside Obsidian."""

from datetime import date, datetime
import hashlib
import os
from pathlib import Path
import re
import stat

MAX_REPORT_BYTES = 512_000
MAX_REPORTS = 2000
MAX_DAYS = 366
DATE_FOLDER = re.compile(r"\d{4}-\d{2}-\d{2}")
EXCLUDED = {"important!.md", "readme.md", "index.md"}
DEFAULT_MODULES = (("AI", None), ("金融", "每日金融"), ("法律", "每日法律"))
MAX_MODULES = 10


def folder_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("请填写 vault 内的日报子目录")
    folder = Path(value.strip())
    if folder.is_absolute() or any(part in ("..", ".") or part.startswith(".") for part in folder.parts) or not folder.parts:
        raise ValueError("日报目录必须是 vault 内的相对子目录")
    return folder.as_posix()


def report_modules(settings: dict) -> list[dict]:
    """Configured report modules; before the list existed, the AI module used ``daily_reports_folder``."""
    modules = settings.get("report_modules")
    if isinstance(modules, list) and modules:
        return [{"name": m["name"], "folder": m["folder"]} for m in modules]
    return [{"name": name, "folder": folder or settings.get("daily_reports_folder") or "每日AI"} for name, folder in DEFAULT_MODULES]


def module_list(value) -> list[dict]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_MODULES:
        raise ValueError(f"日报模块需要 1～{MAX_MODULES} 个")
    result = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError("每个日报模块都需要名称")
        name = item["name"].strip()[:20]
        folder = folder_name(item.get("folder"))
        if any(m["name"] == name or m["folder"] == folder for m in result):
            raise ValueError("日报模块的名称和目录不能重复")
        result.append({"name": name, "folder": folder})
    return result


def module_folder(settings: dict, folder: str | None) -> str:
    folders = [m["folder"] for m in report_modules(settings)]
    if folder is None:
        return folders[0]
    if folder not in folders:
        raise ValueError("不是已配置的日报模块")
    return folder


def report_root(settings: dict, folder: str | None = None) -> Path:
    value = settings.get("obsidian_vault")
    if not value or not Path(value).is_dir():
        raise ValueError("请先在设置中配置可读取的 Obsidian vault")
    vault = Path(value).resolve()
    folder = folder_name(module_folder(settings, folder))
    root = vault
    for part in Path(folder).parts:
        root = root / part
        if root.is_symlink():
            raise ValueError("日报目录不能是符号链接")
    if not root.resolve().is_relative_to(vault) or not root.is_dir():
        raise ValueError("日报目录不存在，请检查设置中的子目录")
    return root


def valid_day(value: str) -> bool:
    try:
        return bool(DATE_FOLDER.fullmatch(value)) and date.fromisoformat(value) <= date.today()
    except ValueError:
        return False


def safe_path(settings: dict, relative: str, folder: str | None = None) -> Path:
    if not isinstance(relative, str):
        raise ValueError("日报路径无效")
    parts = Path(relative).parts
    if len(parts) != 2 or not valid_day(parts[0]) or not parts[1].endswith('.md') or parts[1].lower() in EXCLUDED or parts[1].startswith('.'):
        raise ValueError("只能读取日期目录中的 Markdown 日报")
    root = report_root(settings, folder)
    path = root / relative
    if path.parent.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("日报路径不能越出配置目录或使用符号链接")
    if not path.is_file():
        raise ValueError("日报文件已移动或删除，请刷新列表")
    return path


def read_text(path: Path, limit: int) -> str:
    # O_NOFOLLOW also rejects a file swapped for a symlink just before open.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REPORT_BYTES:
            raise ValueError("日报超过 512 KB 读取上限或不是普通文件，请在 Obsidian 中查看")
        raw = stream.read(limit)
        after = os.fstat(stream.fileno())
        if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("日报正在写入，请稍后刷新")
    return raw.decode('utf-8-sig', errors='strict' if limit > MAX_REPORT_BYTES else 'ignore')


def metadata(path: Path, relative: str, module: dict | None = None) -> dict:
    prefix = read_text(path, 4096)
    # Titles are hints only; the selected article always reads the actual file.
    title = next((line.lstrip('#').strip().strip('*').strip() for line in prefix.splitlines()
                  if line.startswith('# ') or (line.startswith('**') and line.endswith('**'))), path.stem)
    info = path.stat()
    key = relative if module is None else f"{module['folder']}/{relative}"
    return {"id": "report-" + hashlib.sha256(key.encode()).hexdigest()[:24],
            "module": module["name"] if module else None, "folder": module["folder"] if module else None,
            "path": relative, "date": Path(relative).parts[0], "title": title[:240],
            "filename": path.name, "kind": "周报" if "周报" in path.stem or "周度" in title else "日报",
            "modified_at": datetime.fromtimestamp(info.st_mtime).astimezone().isoformat(),
            "version": f"{info.st_mtime_ns}:{info.st_size}", "bytes": info.st_size}


def report_index(settings: dict) -> dict:
    modules = report_modules(settings)
    result = {"reports": [], "dates": [], "latest_date": None, "errors": [], "configured": False, "modules": modules}
    value = settings.get("obsidian_vault")
    if not value or not Path(value).is_dir():
        result["errors"].append("请先在设置中配置可读取的 Obsidian vault")
        return result
    result["configured"] = True
    for module in modules:
        try:
            root = report_root(settings, module["folder"])
        except (ValueError, OSError) as exc:
            result["errors"].append(f"{module['name']}：{exc}")
            continue
        days = sorted((x for x in root.iterdir() if valid_day(x.name) and x.is_dir() and not x.is_symlink()), key=lambda x: x.name, reverse=True)
        if len(days) > MAX_DAYS:
            result["errors"].append(f"{module['name']}：当前展示最近 366 个日期目录，更早报告请在 Obsidian 中查看。")
        for day in days[:MAX_DAYS]:
            paths = sorted(day.glob('*.md'), key=lambda p: (not p.name.startswith('AI日报'), p.name))
            for path in paths:
                if path.name.lower() in EXCLUDED or path.name.startswith('.'):
                    continue
                if len(result["reports"]) >= MAX_REPORTS:
                    result["errors"].append("当前最多展示 2000 篇报告，更早报告请在 Obsidian 中查看。")
                    break
                relative = path.relative_to(root).as_posix()
                try:
                    result["reports"].append(metadata(safe_path(settings, relative, module["folder"]), relative, module))
                except (ValueError, OSError, UnicodeError) as exc:
                    result["errors"].append(f"{module['name']} {relative}：{exc}")
            if len(result["reports"]) >= MAX_REPORTS:
                break
    order = {m["folder"]: i for i, m in enumerate(modules)}
    result["reports"].sort(key=lambda x: (x["date"], -order[x["folder"]]), reverse=True)
    result["dates"] = sorted({x["date"] for x in result["reports"]}, reverse=True)
    result["latest_date"] = next(iter(result["dates"]), None)
    return result


def read_report(settings: dict, relative: str, folder: str | None = None) -> dict:
    try:
        folder = module_folder(settings, folder)
        module = next(m for m in report_modules(settings) if m["folder"] == folder)
        path = safe_path(settings, relative, folder)
        content = read_text(path, MAX_REPORT_BYTES + 1)
        if len(content.encode('utf-8')) > MAX_REPORT_BYTES:
            raise ValueError("日报超过 512 KB 读取上限，请在 Obsidian 中查看")
        return {**metadata(path, relative, module), "content": content, "source": "Obsidian", "read_only": True}
    except (OSError, UnicodeError) as exc:
        raise ValueError("日报暂不可读取或不是有效 UTF-8 文件，请在 Obsidian 中核对后刷新") from exc
