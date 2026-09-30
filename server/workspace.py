"""User-owned records, learning topics and original materials.

Attachments live in SQLite so the existing backup/restore contract stays complete.
No operation in this module starts an agent or reads an external URL.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from .common import identifier, required_text, stamp, synchronized

WORKSPACE_KINDS = ("record", "material", "learning_topic")
WORKSPACE_ACTIONS = (
    "create_record", "update_record", "delete_record", "add_material", "create_learning_topic",
    "update_learning_topic", "link_record", "export_workspace_note",
    "import_obsidian_record",
)
RECORD_TYPES = {"note", "idea", "resource", "status"}
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def optional_text(value, field, limit=10000, strip=True):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{field} 格式无效或过长")
    return value.strip() if strip else value


def web_url(value):
    url = required_text(value, "链接", 4000)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("仅支持不含登录凭据的 HTTP(S) 链接")
    try:
        parsed.port
    except ValueError:
        raise ValueError("链接端口无效") from None
    return url


def file_type(body):
    if body.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise ValueError("仅支持 PDF、PNG、JPEG、GIF、WebP 原文件")


def check_version(item, p):
    if p.get("expected_updated_at") != item["updated_at"]:
        raise ValueError("内容已在别处修改，请重新打开后核对；当前输入仍保留")


class WorkspaceMixin:
    def init_workspace(self):
        self.db.execute("CREATE TABLE IF NOT EXISTS material_blobs (id TEXT PRIMARY KEY, body BLOB NOT NULL)")
        self.db.commit()

    def create_record(self, p):
        content = optional_text(p.get("content"), "记录", 100000, strip=False)
        title = optional_text(p.get("title"), "标题", 200)
        if not content.strip() and not title:
            raise ValueError("请写下一点内容，或用文件名作为标题")
        record_type = p.get("record_type") or "note"
        if not isinstance(record_type, str) or record_type not in RECORD_TYPES:
            raise ValueError("记录类型无效")
        item = self.put("record", {
            "title": title or content.strip().splitlines()[0][:80], "content": content,
            "original_content": content, "record_type": record_type,
            "revision": 1, "created_by": "user", "task_id": None,
            "recall_policy": "normal", "idea_scope": "unknown",
            **({"origin": "topic"} if p.get("origin") == "topic" else {}),
        })
        self.event("RecordCreated", "record", item["id"], details={"title": item["title"]})
        return item

    @synchronized
    def mark_topic_uploads(self):
        """Once: files uploaded from a topic before ``origin`` existed become topic materials."""
        settings = self.get("settings", "settings")
        if not settings or settings.get("topic_uploads_marked"):
            return 0
        linked = {rid for topic in self.all("learning_topic") for rid in topic["record_ids"]}
        marked = 0
        for record in self.all("record"):
            if (record["id"] in linked and record.get("record_type") == "resource" and not record.get("origin")
                    and re.search(r"\.(pdf|md|markdown|txt)$", record["title"], re.I)):
                self.put("record", {**record, "origin": "topic"})
                marked += 1
        self.put("settings", {**settings, "topic_uploads_marked": True})
        return marked

    def import_obsidian_record(self, p):
        topic = self._existing("learning_topic", p)
        relative = required_text(p.get("path"), "笔记路径", 1000)
        vault = self.get("settings", "settings").get("obsidian_vault")
        if not vault or not Path(vault).is_dir():
            raise ValueError("请先配置 Obsidian 仓库")
        root = Path(vault).resolve()
        if Path(relative).is_absolute() or any(part.startswith(".") for part in Path(relative).parts):
            raise ValueError("笔记路径无效")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != ".md" or not path.is_file():
            raise ValueError("笔记必须位于已配置的仓库中")
        try:
            with path.open("rb") as stream:
                body = stream.read(200001)
            if len(body) > 200000:
                raise ValueError("笔记超过 200 KB，请选择所需段落复制到记录")
            content = body.decode("utf-8")
        except (OSError, UnicodeError):
            raise ValueError("无法读取 UTF-8 Markdown 笔记") from None
        record = self.create_record({"title": path.stem[:200], "content": content})
        record["source"] = {"kind": "obsidian", "path": relative, "captured_at": stamp()}
        record = self.put("record", record)
        self.link_record({"id": topic["id"], "record_id": record["id"]})
        return record

    def update_record(self, p):
        item = self._existing("record", p)
        check_version(item, p)
        for field, limit in (("content", 100000), ("title", 200)):
            if field in p:
                item[field] = optional_text(p[field], field, limit, strip=field != "content")
        if not item["title"] and not item["content"].strip():
            raise ValueError("记录不能完全为空")
        item["title"] = item["title"] or item["content"].strip().splitlines()[0][:80]
        if "record_type" in p:
            if not isinstance(p["record_type"], str) or p["record_type"] not in RECORD_TYPES:
                raise ValueError("记录类型无效")
            item["record_type"] = p["record_type"]
        for field, choices in (("idea_scope", ("unknown", "existing", "new_project")), ("recall_policy", ("normal", "never"))):
            if field in p:
                if p[field] not in choices:
                    raise ValueError("回顾偏好无效")
                item[field] = p[field]
        item["revision"] += 1
        saved = self.put("record", item)
        self.event("RecordUpdated", "record", item["id"], details={"title": item["title"]})
        return saved

    def delete_record(self, p):
        """Delete a record with its attachments; things made from it stay but lose the source link."""
        record = self._existing("record", p)
        for material in self.all("material"):
            if material["record_id"] == record["id"]:
                self.db.execute("DELETE FROM material_blobs WHERE id=?", (material["id"],))
                self.delete("material", material["id"])
        for topic in self.all("learning_topic"):
            if record["id"] in topic["record_ids"]:
                self.link_record({"id": topic["id"], "record_id": record["id"], "remove": True})
        for kind in ("todo", "task", "personal_state"):
            for item in self.all(kind):
                previous = item.get("previous_record_ids") or []
                if item.get("record_id") != record["id"] and record["id"] not in previous:
                    continue
                if item.get("record_id") == record["id"]:
                    item["record_id"] = None
                if previous:
                    item["previous_record_ids"] = [rid for rid in previous if rid != record["id"]]
                self.put(kind, item)
        for review in self.all("idea_review"):
            items = [item for item in review["items"] if item["record_id"] != record["id"]]
            if items != review["items"]:
                self.put("idea_review", {**review, "items": items})
        self.delete("record", record["id"])
        self.event("RecordDeleted", "record", record["id"], details={"title": record["title"]})
        return {"deleted": record["id"], "message": "资料已删除" if record.get("origin") == "topic" else "记录已删除"}

    def add_material(self, p):
        record = self._existing("record", {"id": p.get("record_id")})
        material = {"record_id": record["id"], "read_status": "saved", "revision": 1,
                    "read_note": "原件已保存，尚未解析或交给 Agent", "used_in": []}
        body = None
        if p.get("url"):
            material.update({"kind": "link", "url": web_url(p["url"]),
                             "name": optional_text(p.get("name"), "资料名称", 200) or p["url"][:200]})
        else:
            encoded = p.get("base64")
            if not isinstance(encoded, str) or len(encoded) > (MAX_ATTACHMENT_BYTES + 2) // 3 * 4:
                raise ValueError("每个附件不得超过 20 MB")
            try:
                body = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise ValueError("附件编码无效") from None
            if not body or len(body) > MAX_ATTACHMENT_BYTES:
                raise ValueError("附件为空或超过 20 MB")
            mime, extension = file_type(body)
            name = required_text(p.get("name"), "文件名", 200)
            name = re.sub(r"[\x00-\x1f/\\]", "_", name)
            material.update({"kind": "pdf" if mime == "application/pdf" else "image", "mime": mime,
                             "extension": extension, "name": name, "size": len(body),
                             "sha256": hashlib.sha256(body).hexdigest()})
        material["id"] = identifier()
        # put commits both the pending blob and its metadata in one transaction.
        if body is not None:
            self.db.execute("INSERT INTO material_blobs VALUES(?, ?)", (material["id"], body))
        try:
            saved = self.put("material", material)
        except Exception:
            self.db.rollback()
            raise
        self.event("MaterialSaved", "record", record["id"], details={"material_id": saved["id"], "title": saved["name"]})
        return saved

    @synchronized
    def material_original(self, material_id):
        material = self._existing("material", {"id": material_id})
        row = self.db.execute("SELECT body FROM material_blobs WHERE id=?", (material_id,)).fetchone()
        if row is None:
            raise ValueError("原文件不存在；链接资料请访问原网址")
        return material, bytes(row[0])

    def export_blobs(self):
        return [{"id": row[0], "base64": base64.b64encode(row[1]).decode("ascii")}
                for row in self.db.execute("SELECT id,body FROM material_blobs")]

    def create_learning_topic(self, p):
        record = self._existing("record", {"id": p["record_id"]}) if p.get("record_id") else None
        title = required_text(p.get("title") or (record and record["title"]), "主题标题", 200)
        mode = p.get("mode") or "guided"
        if mode not in ("quick", "guided"):
            raise ValueError("学习方式无效")
        item = self.put("learning_topic", {
            "title": title, "goal": optional_text(p.get("goal"), "学习目标", 3000),
            "mode": mode, "agent": "codex", "record_ids": [record["id"]] if record else [],
            "native_session_id": None, "revision": 1,
        })
        self.event("LearningTopicCreated", "learning_topic", item["id"], details={"title": title})
        return item

    def update_learning_topic(self, p):
        item = self._existing("learning_topic", p)
        check_version(item, p)
        if "title" in p:
            item["title"] = required_text(p["title"], "主题标题", 200)
        if "goal" in p:
            item["goal"] = optional_text(p["goal"], "学习目标", 3000)
        if "mode" in p:
            if p["mode"] not in ("guided", "quick"):
                raise ValueError("学习方式无效")
            item["mode"] = p["mode"]
        if p.get("agent", "codex") != "codex":
            raise ValueError("当前仅接入 Codex，不会自动切换 Agent")
        item["revision"] += 1
        return self.put("learning_topic", item)

    def link_record(self, p):
        topic = self._existing("learning_topic", p)
        record = self._existing("record", {"id": p.get("record_id")})
        ids = topic["record_ids"]
        if p.get("remove"):
            ids = [item for item in ids if item != record["id"]]
        elif record["id"] not in ids:
            ids = [*ids, record["id"]]
        if ids != topic["record_ids"]:
            topic.update(record_ids=ids, revision=topic["revision"] + 1)
            topic = self.put("learning_topic", topic)
        return topic

    @synchronized
    def workspace_markdown(self, kind, object_id):
        if kind not in ("record", "learning_topic"):
            raise ValueError("导出类型无效")
        item = self._existing(kind, {"id": object_id})
        text = f"# {item['title']}\n\n"
        if kind == "record":
            text += item["content"] + "\n"
            materials = [m for m in self.all("material") if m["record_id"] == object_id]
        else:
            text += item["goal"] + "\n"
            materials = [m for m in self.all("material") if m["record_id"] in item["record_ids"]]
            report = self.get("learning_summary", object_id + "-summary")
            if report:
                from .learning_summary import SECTION_TITLES
                text += "\n" + self.summary_view(object_id)["evidence"] + "\n"
                for key, title in SECTION_TITLES.items():
                    section = report["sections"].get(key)
                    if not section or not section["body"]:
                        continue
                    suffix = " · 我的计划" if key == "next" and section.get("owner") == "user_plan" else " · AI 建议" if key == "next" else ""
                    text += f"\n## {title}{suffix}\n\n{section['body']}\n"
                    if section.get("manual"):
                        text += "\n*人工修订，自动更新不会覆盖。*\n"
                    for source in section.get("sources", []):
                        if source["kind"] == "material":
                            material = self.get("material", source["id"])
                            if material and material["id"] not in {m["id"] for m in materials}:
                                materials.append(material)
                            link = source.get("url") or (f"{source['id']}{material['extension']}" if material else "")
                            if source.get("page"):
                                link += f"#page={source['page']}"
                        elif source["kind"] == "message":
                            link = f"#message-{source['id']}"
                        else:
                            link = ""
                        label = source["title"].replace("[", "\\[").replace("]", "\\]")
                        text += f"\n> 来源：[{label}](<{link}>) · 版本 {source['revision']}\n" if link else f"\n> 来源：{label} · 版本 {source['revision']}\n"
                text += f"\n来源截止：{report.get('cutoff', '人工记录')}\n"
                coverage = report.get("coverage", {})
                if coverage.get("omitted_messages") or coverage.get("partial_sources"):
                    text += f"\n覆盖说明：{coverage.get('omitted_messages', 0)} 条较早消息未纳入，{coverage.get('partial_sources', 0)} 份来源仅纳入部分文字。\n"
                referenced = {source["id"]: source for section in report["sections"].values() for source in section.get("sources", []) if source["kind"] == "message"}
                for source in referenced.values():
                    text += f"\n<a id=\"message-{source['id']}\"></a>\n### 原话：{source['title']}\n\n{source['text']}\n"
            for rid in item["record_ids"]:
                record = self.get("record", rid)
                if record:
                    text += f"\n## 相关记录：{record['title']}\n\n{record['content']}\n"
        for material in materials:
            name = material["name"].replace("[", "\\[").replace("]", "\\]")
            target = material.get("url") or f"{material['id']}{material['extension']}"
            text += f"\n- [{name}](<{target}>) — {material['read_note']}\n"
        text += f"\n---\n主版本：Personal OS · {kind}/{object_id}\n记录时间：{item['created_at']}\n导出时间：{stamp()}\n"
        return item, text, materials

    def export_workspace_note(self, p):
        item, text, materials = self.workspace_markdown(p.get("kind", "record"), p.get("id"))
        if p.get("destination") == "obsidian":
            vault = self.get("settings", "settings").get("obsidian_vault")
            if not vault or not Path(vault).is_dir():
                raise ValueError("请先在设置中配置 Obsidian 仓库")
            root = Path(vault).resolve()
            folder = root / "Personal-OS"
            if folder.is_symlink():
                raise ValueError("导出目录不能是符号链接")
        else:
            root = self.path.parent.resolve()
            folder = root / "exports"
        if folder.is_symlink():
            raise ValueError("导出目录不能是符号链接")
        folder.mkdir(exist_ok=True)
        bundle = folder / f"note-{identifier()}"
        bundle.mkdir(mode=0o700)
        name = re.sub(r"[\x00-\x1f/\\:*?\"<>|]", "_", item["title"])[:80].strip(". ") or "记录"
        destination = bundle / f"{name}.md"
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(text)
        for material in materials:
            if material["kind"] != "link":
                _, body = self.material_original(material["id"])
                (bundle / f"{material['id']}{material['extension']}").write_bytes(body)
        return {"path": str(destination), "message": "已导出 Markdown 和原附件；Personal OS 仍为主版本"}
