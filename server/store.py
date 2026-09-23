"""SQLite-backed Personal Work Graph and explicit user actions."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any


KINDS = (
    "project", "task", "daily_plan", "daily_log", "decision", "agent_run",
    "artifact", "intelligence_channel", "intelligence_item", "personal_rule",
    "knowledge_proposal", "settings",
)
TASK_STATES = {"Inbox", "Planned", "Running", "Review", "Done", "Blocked"}
TASK_SOURCES = {"Manual", "Morning Brief", "Intelligence", "Project", "Agent Suggestion", "Yesterday Carryover"}
DEFAULT_SETTINGS = {
    "theme_mode": "auto", "manual_theme": "morning", "nickname": "博士",
    "obsidian_vault": "", "motion": "low",
}


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def local_day() -> str:
    return date.today().isoformat()


def identifier() -> str:
    return uuid.uuid4().hex


def required_text(value: Any, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 不能为空")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"{field} 过长")
    return text


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS objects (
              kind TEXT NOT NULL, id TEXT NOT NULL PRIMARY KEY,
              data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS objects_kind ON objects(kind);
            CREATE TABLE IF NOT EXISTS activity (
              id TEXT PRIMARY KEY, type TEXT NOT NULL, subject_kind TEXT,
              subject_id TEXT, project_id TEXT, details TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS activity_time ON activity(created_at);
        """)
        if not self.get("settings", "settings"):
            self.put("settings", {"id": "settings", **DEFAULT_SETTINGS})

    def close(self) -> None:
        self.db.close()

    def get(self, kind: str, object_id: str) -> dict[str, Any] | None:
        if kind not in KINDS:
            raise ValueError("未知对象类型")
        row = self.db.execute(
            "SELECT data FROM objects WHERE kind=? AND id=?", (kind, object_id)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    def all(self, kind: str) -> list[dict[str, Any]]:
        if kind not in KINDS:
            raise ValueError("未知对象类型")
        rows = self.db.execute(
            "SELECT data FROM objects WHERE kind=? ORDER BY created_at DESC", (kind,)
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def put(self, kind: str, value: dict[str, Any]) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError("未知对象类型")
        object_id = value.get("id") or identifier()
        now = stamp()
        previous = self.get(kind, object_id)
        item = {**value, "id": object_id, "created_at": previous.get("created_at", now) if previous else now, "updated_at": now}
        self.db.execute(
            "INSERT INTO objects(kind,id,data,created_at,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (kind, object_id, json.dumps(item, ensure_ascii=False), item["created_at"], now),
        )
        self.db.commit()
        return item

    def delete(self, kind: str, object_id: str) -> None:
        self.db.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, object_id))
        self.db.commit()

    def event(self, event_type: str, subject_kind: str | None = None,
              subject_id: str | None = None, project_id: str | None = None,
              details: dict[str, Any] | None = None) -> None:
        self.db.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?,?)",
            (identifier(), event_type, subject_kind, subject_id, project_id,
             json.dumps(details or {}, ensure_ascii=False), stamp()),
        )
        self.db.commit()

    def events(self, day: str | None = None) -> list[dict[str, Any]]:
        if day:
            rows = self.db.execute(
                "SELECT * FROM activity WHERE substr(created_at,1,10)=? ORDER BY created_at DESC", (day,)
            ).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM activity ORDER BY created_at DESC LIMIT 1000").fetchall()
        return [{**dict(row), "details": json.loads(row["details"])} for row in rows]

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                **{kind + "s": self.all(kind) for kind in KINDS if kind != "settings"},
                "settings": self.get("settings", "settings"),
                "events": self.events(),
                "today": local_day(),
                "brief": self.brief(),
            }

    def brief(self) -> list[dict[str, Any]]:
        today = local_day()
        tasks = [t for t in self.all("task") if t["status"] not in ("Done", "Blocked")]
        tasks.sort(key=lambda t: (
            t.get("deadline") or "9999-12-31",
            0 if t.get("priority") == "High" else 1,
            t.get("created_at", ""),
        ))
        choices = []
        for task in tasks[:3]:
            project = self.get("project", task["project_id"]) if task.get("project_id") else None
            reason = ("截止日期临近" if task.get("deadline") and task["deadline"] <= today
                      else "昨日遗留，适合继续推进" if task.get("planned_date") and task["planned_date"] < today
                      else f"关联项目：{project['name']}" if project else "尚未安排，建议确认优先级")
            choices.append({"task_id": task["id"], "title": task["title"], "reason": reason})
        return choices

    def action(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是对象")
        with self.lock:
            dispatch = {
                "create_project": self.create_project,
                "update_project": self.update_project,
                "create_task": self.create_task,
                "update_task": self.update_task,
                "complete_task": self.complete_task,
                "confirm_plan": self.confirm_plan,
                "create_decision": self.create_decision,
                "update_decision": self.update_decision,
                "draft_log": self.draft_log,
                "update_log": self.update_log,
                "confirm_log": self.confirm_log,
                "create_channel": self.create_channel,
                "update_channel": self.update_channel,
                "create_intelligence": self.create_intelligence,
                "feedback_intelligence": self.feedback_intelligence,
                "create_rule": self.create_rule,
                "update_rule": self.update_rule,
                "delete_rule": self.delete_rule,
                "save_settings": self.save_settings,
                "propose_knowledge": self.propose_knowledge,
                "approve_knowledge": self.approve_knowledge,
            }
            if name not in dispatch:
                raise ValueError("未知操作")
            return dispatch[name](payload)

    def create_project(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self.put("project", {
            "name": required_text(p.get("name"), "项目名称", 120),
            "description": (p.get("description") or "").strip()[:2000],
            "status": "Active", "stage": (p.get("stage") or "规划中").strip()[:120],
            "pulse": "", "workspace_path": (p.get("workspace_path") or "").strip(),
        })
        self.event("ProjectCreated", "project", item["id"], item["id"], {"name": item["name"]})
        return item

    def update_project(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("project", p)
        for field in ("name", "description", "status", "stage", "pulse", "workspace_path"):
            if field in p:
                item[field] = str(p[field]).strip()
        if item["status"] not in ("Active", "Paused", "Completed"):
            raise ValueError("项目状态无效")
        item["name"] = required_text(item["name"], "项目名称", 120)
        item = self.put("project", item)
        self.event("ProjectUpdated", "project", item["id"], item["id"], {"name": item["name"]})
        return item

    def create_task(self, p: dict[str, Any]) -> dict[str, Any]:
        project_id = p.get("project_id") or None
        if project_id and not self.get("project", project_id):
            raise ValueError("项目不存在")
        source = p.get("source") or "Manual"
        if source not in TASK_SOURCES:
            raise ValueError("任务来源无效")
        item = self.put("task", {
            "title": required_text(p.get("title"), "任务标题", 200),
            "description": (p.get("description") or "").strip()[:10000],
            "status": "Inbox", "priority": p.get("priority") if p.get("priority") in ("High", "Medium", "Low") else "Medium",
            "project_id": project_id, "source": source, "planned_date": None,
            "deadline": p.get("deadline") or None, "executor_type": "self", "agent_id": None,
            "result": "", "review_status": None, "created_by": "user",
        })
        self.event("TaskCreated", "task", item["id"], project_id, {"title": item["title"], "source": source})
        return item

    def update_task(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("task", p)
        for field in ("title", "description", "priority", "deadline", "project_id", "executor_type"):
            if field in p:
                item[field] = p[field]
        item["title"] = required_text(item["title"], "任务标题", 200)
        if item["priority"] not in ("High", "Medium", "Low"):
            raise ValueError("优先级无效")
        if item.get("project_id") and not self.get("project", item["project_id"]):
            raise ValueError("项目不存在")
        if item["executor_type"] not in ("self", "agent"):
            raise ValueError("执行方式无效")
        item = self.put("task", item)
        self.event("TaskUpdated", "task", item["id"], item.get("project_id"), {"title": item["title"]})
        return item

    def complete_task(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("task", p)
        if item["executor_type"] == "agent":
            raise ValueError("Agent 任务必须经过审核")
        if item["status"] not in ("Inbox", "Planned", "Running"):
            raise ValueError("当前任务状态不能直接完成")
        item["status"] = "Done"
        item["completed_at"] = stamp()
        item = self.put("task", item)
        self.event("TaskCompleted", "task", item["id"], item.get("project_id"), {"title": item["title"]})
        return item

    def confirm_plan(self, p: dict[str, Any]) -> dict[str, Any]:
        day = p.get("date") or local_day()
        if day != local_day():
            raise ValueError("只能确认今天的计划")
        task_ids = p.get("task_ids")
        if not isinstance(task_ids, list) or len(task_ids) != len(set(task_ids)):
            raise ValueError("计划任务无效")
        tasks = [self.get("task", task_id) for task_id in task_ids]
        if any(task is None or task["status"] in ("Done", "Blocked") for task in tasks):
            raise ValueError("计划包含不存在或不能安排的任务")
        plan = next((x for x in self.all("daily_plan") if x["date"] == day), None)
        if plan and plan.get("confirmed_at"):
            raise ValueError("今日计划已确认")
        for task in tasks:
            task["planned_date"] = day
            if task["status"] == "Inbox":
                task["status"] = "Planned"
            self.put("task", task)
        plan = self.put("daily_plan", {"id": plan["id"] if plan else identifier(), "date": day, "task_ids": task_ids, "confirmed_at": stamp()})
        self.event("DailyPlanConfirmed", "daily_plan", plan["id"], details={"task_ids": task_ids})
        return plan

    def create_decision(self, p: dict[str, Any]) -> dict[str, Any]:
        project_id = p.get("project_id") or None
        if project_id and not self.get("project", project_id):
            raise ValueError("项目不存在")
        item = self.put("decision", {
            "title": required_text(p.get("title"), "决策标题", 200),
            "content": required_text(p.get("content") or p.get("title"), "决策内容", 5000),
            "reason": (p.get("reason") or "").strip()[:2000],
            "project_id": project_id, "task_id": p.get("task_id") or None,
            "status": "Active", "decided_at": stamp(),
        })
        self.event("DecisionCreated", "decision", item["id"], project_id, {"title": item["title"]})
        return item

    def update_decision(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("decision", p)
        for field in ("title", "content", "reason", "status"):
            if field in p:
                item[field] = str(p[field]).strip()
        if item["status"] not in ("Active", "Superseded", "Archived"):
            raise ValueError("决策状态无效")
        item = self.put("decision", item)
        self.event("DecisionUpdated", "decision", item["id"], item.get("project_id"), {"title": item["title"], "status": item["status"]})
        return item

    def draft_log(self, p: dict[str, Any]) -> dict[str, Any]:
        day = p.get("date") or local_day()
        log = next((x for x in self.all("daily_log") if x["date"] == day), None)
        if log and log.get("confirmed_at"):
            raise ValueError("日报已经确认")
        events = self.events(day)
        done = [e["details"].get("title", "任务") for e in reversed(events) if e["type"] == "TaskCompleted"]
        decisions = [e["details"].get("title", "决策") for e in reversed(events) if e["type"] == "DecisionCreated"]
        artifact_names = [e["details"].get("name", "产物") for e in reversed(events) if e["type"] == "ArtifactCreated"]
        unfinished = [t["title"] for t in self.all("task") if t.get("planned_date") == day and t["status"] not in ("Done", "Blocked")]
        summary = "今天完成：\n" + ("\n".join(f"- {x}" for x in done) or "- 暂无")
        if decisions:
            summary += "\n\n今日决策：\n" + "\n".join(f"- {x}" for x in decisions)
        if artifact_names:
            summary += "\n\n产物：\n" + "\n".join(f"- {x}" for x in artifact_names)
        if unfinished:
            summary += "\n\n未完成：\n" + "\n".join(f"- {x}" for x in unfinished)
        item = self.put("daily_log", {"id": log["id"] if log else identifier(), "date": day, "summary": summary, "source_event_ids": [e["id"] for e in events], "confirmed_at": None})
        self.event("DailyLogDrafted", "daily_log", item["id"], details={"date": day})
        return item

    def update_log(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("daily_log", p)
        if item.get("confirmed_at"):
            raise ValueError("日报已封存")
        item["summary"] = required_text(p.get("summary"), "日报内容", 20000)
        item = self.put("daily_log", item)
        self.event("DailyLogEdited", "daily_log", item["id"], details={"date": item["date"]})
        return item

    def confirm_log(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("daily_log", p)
        if item.get("confirmed_at"):
            raise ValueError("日报已确认")
        item["confirmed_at"] = stamp()
        item = self.put("daily_log", item)
        self.event("DailyLogConfirmed", "daily_log", item["id"], details={"date": item["date"]})
        return item

    def create_channel(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self.put("intelligence_channel", {
            "name": required_text(p.get("name"), "频道名称", 80),
            "boundary": (p.get("boundary") or "").strip()[:2000],
            "sources": (p.get("sources") or "").strip()[:2000],
            "filter_rule": (p.get("filter_rule") or "").strip()[:2000],
            "daily_limit": max(1, min(50, int(p.get("daily_limit") or 8))),
        })
        self.event("IntelligenceChannelCreated", "intelligence_channel", item["id"], details={"name": item["name"]})
        return item

    def update_channel(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("intelligence_channel", p)
        for field in ("name", "boundary", "sources", "filter_rule"):
            if field in p:
                item[field] = str(p[field]).strip()
        if "daily_limit" in p:
            item["daily_limit"] = max(1, min(50, int(p["daily_limit"])))
        item["name"] = required_text(item["name"], "频道名称", 80)
        item = self.put("intelligence_channel", item)
        self.event("IntelligenceChannelUpdated", "intelligence_channel", item["id"], details={"name": item["name"]})
        return item

    def create_intelligence(self, p: dict[str, Any]) -> dict[str, Any]:
        channel = self.get("intelligence_channel", p.get("channel_id") or "")
        if not channel:
            raise ValueError("频道不存在")
        item = self.put("intelligence_item", {
            "title": required_text(p.get("title"), "标题", 300),
            "source": required_text(p.get("source"), "来源", 200),
            "url": (p.get("url") or "").strip()[:2000],
            "summary": (p.get("summary") or "").strip()[:5000],
            "why_recommended": required_text(p.get("why_recommended"), "推荐原因", 1000),
            "channel_id": channel["id"], "project_id": p.get("project_id") or None,
            "published_at": p.get("published_at") or stamp(),
            "feedback": "unread",
        })
        self.event("IntelligenceItemAdded", "intelligence_item", item["id"], item.get("project_id"), {"title": item["title"]})
        return item

    def feedback_intelligence(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("intelligence_item", p)
        if p.get("feedback") not in ("read", "ignore", "save", "deep_research"):
            raise ValueError("反馈操作无效")
        item["feedback"] = p["feedback"]
        item = self.put("intelligence_item", item)
        self.event("IntelligenceFeedback", "intelligence_item", item["id"], item.get("project_id"), {"feedback": item["feedback"]})
        return item

    def create_rule(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self.put("personal_rule", {"text": required_text(p.get("text"), "规则内容", 1000), "category": p.get("category") or "General", "enabled": True})
        self.event("PersonalRuleCreated", "personal_rule", item["id"], details={"text": item["text"]})
        return item

    def update_rule(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("personal_rule", p)
        if "text" in p:
            item["text"] = required_text(p["text"], "规则内容", 1000)
        if "enabled" in p:
            item["enabled"] = bool(p["enabled"])
        item = self.put("personal_rule", item)
        self.event("PersonalRuleUpdated", "personal_rule", item["id"], details={"enabled": item["enabled"]})
        return item

    def delete_rule(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("personal_rule", p)
        self.delete("personal_rule", item["id"])
        self.event("PersonalRuleDeleted", "personal_rule", item["id"])
        return {"deleted": item["id"]}

    def save_settings(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self.get("settings", "settings") or {"id": "settings", **DEFAULT_SETTINGS}
        for field in ("theme_mode", "manual_theme", "nickname", "obsidian_vault", "motion"):
            if field in p:
                item[field] = str(p[field]).strip()
        if item["theme_mode"] not in ("auto", "manual") or item["manual_theme"] not in ("morning", "afternoon", "night"):
            raise ValueError("主题设置无效")
        item["nickname"] = item["nickname"][:50]
        if item["obsidian_vault"] and not Path(item["obsidian_vault"]).is_dir():
            raise ValueError("Obsidian vault 路径不存在")
        item = self.put("settings", item)
        self.event("SettingsUpdated", "settings", "settings", details={"fields": list(p)})
        return item

    def propose_knowledge(self, p: dict[str, Any]) -> dict[str, Any]:
        task = self.get("task", p.get("task_id") or "")
        if not task:
            raise ValueError("任务不存在")
        item = self.put("knowledge_proposal", {
            "task_id": task["id"], "title": required_text(p.get("title"), "知识标题", 200),
            "content": required_text(p.get("content"), "知识内容", 20000),
            "status": "Review", "path": None,
        })
        self.event("KnowledgeProposed", "knowledge_proposal", item["id"], task.get("project_id"), {"title": item["title"]})
        return item

    def approve_knowledge(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("knowledge_proposal", p)
        if item["status"] != "Review":
            raise ValueError("这条提案已经处理")
        choice = p.get("choice")
        if choice not in ("write", "keep", "discard"):
            raise ValueError("知识审核选择无效")
        if choice == "write":
            settings = self.get("settings", "settings") or {}
            vault = Path(settings.get("obsidian_vault") or "")
            if not settings.get("obsidian_vault") or not vault.is_dir():
                raise ValueError("请先在设置中配置 Obsidian vault")
            title = required_text(p.get("title") or item["title"], "知识标题", 200)
            content = required_text(p.get("content") or item["content"], "知识内容", 20000)
            safe_name = re.sub(r"[/\\:\x00-\x1f]", "-", title).strip(" .")
            if not safe_name or safe_name in (".", ".."):
                raise ValueError("知识标题不能作为文件名")
            destination = vault / "Personal-OS" / f"{safe_name}.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with destination.open("x", encoding="utf-8") as stream:
                    stream.write(f"# {title}\n\n{content}\n")
            except FileExistsError as exc:
                raise ValueError("知识库中已存在同名文件，请修改标题") from exc
            item["title"], item["content"], item["path"] = title, content, str(destination)
        item["status"] = {"write": "Written", "keep": "KeptInTask", "discard": "Discarded"}[choice]
        item = self.put("knowledge_proposal", item)
        task = self.get("task", item["task_id"])
        self.event("KnowledgeReviewed", "knowledge_proposal", item["id"], task.get("project_id") if task else None, {"choice": choice, "title": item["title"]})
        return item

    def _existing(self, kind: str, p: dict[str, Any]) -> dict[str, Any]:
        item = self.get(kind, p.get("id") or "")
        if not item:
            raise ValueError("对象不存在")
        return item
