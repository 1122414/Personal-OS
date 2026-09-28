"""SQLite-backed Personal Work Graph and explicit user actions."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import uuid
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any

from .feeds import fetch_feed


KINDS = (
    "project", "task", "daily_plan", "daily_log", "decision", "agent_run",
    "artifact", "intelligence_channel", "intelligence_item", "personal_rule",
    "knowledge_proposal", "daily_brief", "settings",
)
TASK_STATES = {"Inbox", "Planned", "Running", "Review", "Done", "Blocked"}
TASK_SOURCES = {"Manual", "Morning Brief", "Intelligence", "Project", "Agent Suggestion", "Yesterday Carryover"}
DEFAULT_SETTINGS = {
    "theme_mode": "auto", "manual_theme": "morning", "nickname": "博士",
    "obsidian_vault": "", "motion": "low",
}


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def local_day() -> str:
    return date.today().isoformat()


def past_or_today(value: Any) -> str:
    try:
        day = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("日期格式必须为 YYYY-MM-DD") from None
    if day > date.today():
        raise ValueError("不能选择未来日期")
    return day.isoformat()


def identifier() -> str:
    return uuid.uuid4().hex


def required_text(value: Any, field: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 不能为空")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"{field} 过长")
    return text


def synchronized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return guarded


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
        self._processes: dict[str, subprocess.Popen] = {}
        self._workers: dict[str, threading.Thread] = {}
        self._stopping = False
        self._recover_interrupted_runs()

    def close(self) -> None:
        with self.lock:
            self._stopping = True
            for run in self.all("agent_run"):
                if run.get("status") != "Running":
                    continue
                process = self._processes.get(run["id"])
                if process and process.poll() is None:
                    process.terminate()
                run["status"] = "Interrupted"
                run["error"] = "客户端已关闭，执行中断。请检查工作目录后重试。"
                run["finished_at"] = stamp()
                self.put("agent_run", run)
                task = self.get("task", run["task_id"])
                if task and task["status"] == "Running":
                    task["status"] = "Blocked"
                    self.put("task", task)
                self.event("AgentRunInterrupted", "agent_run", run["id"], task.get("project_id") if task else None)
            workers = list(self._workers.values())
        for worker in workers:
            worker.join(timeout=5)
        with self.lock:
            processes = list(self._processes.values())
        for process in processes:
            if process.poll() is None:
                process.kill()
        for worker in workers:
            if worker.is_alive():
                worker.join(timeout=5)
        with self.lock:
            self.db.close()

    @synchronized
    def get(self, kind: str, object_id: str) -> dict[str, Any] | None:
        if kind not in KINDS:
            raise ValueError("未知对象类型")
        row = self.db.execute(
            "SELECT data FROM objects WHERE kind=? AND id=?", (kind, object_id)
        ).fetchone()
        return json.loads(row["data"]) if row else None

    @synchronized
    def all(self, kind: str) -> list[dict[str, Any]]:
        if kind not in KINDS:
            raise ValueError("未知对象类型")
        rows = self.db.execute(
            "SELECT data FROM objects WHERE kind=? ORDER BY created_at DESC", (kind,)
        ).fetchall()
        return [json.loads(row["data"]) for row in rows]

    @synchronized
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

    @synchronized
    def delete(self, kind: str, object_id: str) -> None:
        self.db.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, object_id))
        self.db.commit()

    @synchronized
    def event(self, event_type: str, subject_kind: str | None = None,
              subject_id: str | None = None, project_id: str | None = None,
              details: dict[str, Any] | None = None) -> None:
        self.db.execute(
            "INSERT INTO activity VALUES(?,?,?,?,?,?,?)",
            (identifier(), event_type, subject_kind, subject_id, project_id,
             json.dumps(details or {}, ensure_ascii=False), stamp()),
        )
        self.db.commit()

    @synchronized
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
            result = {
                **{kind + "s": self.all(kind) for kind in KINDS if kind != "settings"},
                "settings": self.get("settings", "settings"),
                "events": self.events(),
                "today": local_day(),
                "brief": self.brief(),
                "runtime": {"codex_available": bool(shutil.which("codex"))},
            }
            result["history_dates"] = self.history_dates()
            result["daily_logs"] = [self.log_view(log) for log in result["daily_logs"]]
            result["projects"] = [{**project, "pulse_stale": self.pulse_stale(project)} for project in result["projects"]]
            result["agent_runs"] = [{k: v for k, v in run.items() if k != "before_snapshot"} for run in result["agent_runs"]]
            return result

    @synchronized
    def history_dates(self) -> list[str]:
        days = {row[0] for row in self.db.execute("SELECT DISTINCT substr(created_at,1,10) FROM activity")}
        days.update(log["date"] for log in self.all("daily_log"))
        return sorted(days | {local_day()}, reverse=True)

    @synchronized
    def history(self, day: str) -> dict[str, Any]:
        day = past_or_today(day)
        log = next((x for x in self.all("daily_log") if x["date"] == day), None)
        return {"date": day, "events": self.events(day), "log": self.log_view(log) if log else None}

    def log_events(self, day: str) -> list[dict[str, Any]]:
        return [event for event in self.events(day) if event["type"].startswith(
            ("Task", "Agent", "Artifact", "Decision", "Obsidian", "DailyPlan", "ExternalRecord"))]

    def log_view(self, log: dict[str, Any]) -> dict[str, Any]:
        known = set(log.get("source_event_ids", []))
        stale = any(event["id"] not in known for event in self.log_events(log["date"]))
        return {**log, "stale": stale, "latest_source_event_ids": [e["id"] for e in self.log_events(log["date"])]}

    def pulse_stale(self, project: dict[str, Any]) -> bool:
        generated = project.get("pulse_generated_at")
        if not generated:
            return True
        latest = self.db.execute(
            "SELECT max(created_at) FROM activity WHERE project_id=? AND type NOT IN ('ProjectPulseGenerated','ProjectPulseFailed')",
            (project["id"],),
        ).fetchone()[0]
        return bool(latest and latest > generated)

    def brief(self) -> list[dict[str, Any]]:
        today = local_day()
        generated = next((x for x in self.all("daily_brief") if x["date"] == today), None)
        if generated:
            valid = {t["id"]: t for t in self.all("task") if t["status"] in ("Inbox", "Planned") and not t.get("archived_at")}
            choices = [{**item, "title": valid[item["task_id"]]["title"]} for item in generated["priorities"] if item["task_id"] in valid]
            if choices:
                return choices
        tasks = [t for t in self.all("task") if t["status"] in ("Inbox", "Planned") and not t.get("archived_at")]
        tasks.sort(key=lambda t: (
            t.get("deadline") or "9999-12-31",
            0 if t.get("priority") == "High" else 1,
            t.get("created_at", ""),
        ))
        choices = []
        for task in tasks[:3]:
            project = self.get("project", task["project_id"]) if task.get("project_id") else None
            decision = next((d for d in self.all("decision") if d["status"] == "Active" and d.get("project_id") == task.get("project_id")), None) if project else None
            reason = ("截止日期临近" if task.get("deadline") and task["deadline"] <= today
                      else "昨日遗留，适合继续推进" if task.get("planned_date") and task["planned_date"] < today
                      else f"关联项目：{project['name']}" if project else "尚未安排，建议确认优先级")
            if decision:
                reason += f"；当前决策：{decision['title']}"
            choices.append({"task_id": task["id"], "title": task["title"], "reason": reason})
        return choices

    def action(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是对象")
        dispatch = {
                "create_project": self.create_project,
                "update_project": self.update_project,
                "create_task": self.create_task,
                "update_task": self.update_task,
                "complete_task": self.complete_task,
                "confirm_plan": self.confirm_plan,
                "add_to_today": self.add_to_today,
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
                "start_agent": self.start_agent,
                "cancel_agent": self.cancel_agent,
                "review_agent": self.review_agent,
                "generate_brief": self.generate_brief,
                "scan_obsidian": self.scan_obsidian,
                "refresh_channel": self.refresh_channel,
                "research_intelligence": self.research_intelligence,
                "generate_project_pulse": self.generate_project_pulse,
                "summarize_log": self.summarize_log,
        }
        if name not in dispatch:
            raise ValueError("未知操作")
        if name in ("refresh_channel", "generate_brief", "generate_project_pulse", "summarize_log"):
            return dispatch[name](payload)
        with self.lock:
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
        if "pulse" in p:
            item["pulse_manual"] = True
            item["pulse_generated_at"] = stamp()
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
            "deadline": p.get("deadline") or None,
            "executor_type": p.get("executor_type") if p.get("executor_type") in ("self", "agent") else "self",
            "agent_id": "Codex" if p.get("executor_type") == "agent" else None,
            "result": "", "review_status": None, "created_by": "user",
        })
        self.event("TaskCreated", "task", item["id"], project_id, {"title": item["title"], "source": source})
        return item

    def update_task(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("task", p)
        if item["status"] in ("Running", "Review") and "executor_type" in p and p["executor_type"] != item["executor_type"]:
            raise ValueError("执行中的 Agent 任务不能改变执行方式")
        for field in ("title", "description", "priority", "deadline", "project_id", "executor_type", "agent_id"):
            if field in p:
                item[field] = p[field]
        item["title"] = required_text(item["title"], "任务标题", 200)
        if item["priority"] not in ("High", "Medium", "Low"):
            raise ValueError("优先级无效")
        if item.get("project_id") and not self.get("project", item["project_id"]):
            raise ValueError("项目不存在")
        if item["executor_type"] not in ("self", "agent"):
            raise ValueError("执行方式无效")
        item["agent_id"] = "Codex" if item["executor_type"] == "agent" else None
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

    def add_to_today(self, p: dict[str, Any]) -> dict[str, Any]:
        task = self.get("task", p.get("task_id") or "")
        if not task or task["status"] in ("Done", "Blocked"):
            raise ValueError("任务不存在或当前不能安排")
        plan = next((x for x in self.all("daily_plan") if x["date"] == local_day() and x.get("confirmed_at")), None)
        if not plan:
            raise ValueError("请先确认今日计划")
        if task["id"] not in plan["task_ids"]:
            plan["task_ids"].append(task["id"])
            self.put("daily_plan", plan)
        task["planned_date"] = local_day()
        if task["status"] == "Inbox":
            task["status"] = "Planned"
        task = self.put("task", task)
        self.event("TaskAddedToToday", "task", task["id"], task.get("project_id"), {"title": task["title"]})
        return task

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
        day = past_or_today(p.get("date") or local_day())
        log = next((x for x in self.all("daily_log") if x["date"] == day), None)
        if log and log.get("confirmed_at"):
            raise ValueError("日报已经确认")
        if log and not p.get("regenerate"):
            return log
        if day == local_day():
            self.scan_obsidian({"date": day})
        events = self.log_events(day)
        done = [e["details"].get("title", "任务") for e in reversed(events) if e["type"] == "TaskCompleted"]
        decisions = [e["details"].get("title", "决策") for e in reversed(events) if e["type"] == "DecisionCreated"]
        artifact_names = [e["details"].get("name", "产物") for e in reversed(events) if e["type"] == "ArtifactCreated"]
        changed_notes = [e["details"].get("path", "笔记") for e in reversed(events) if e["type"] == "ObsidianFileChanged"]
        plan = next((x for x in self.all("daily_plan") if x["date"] == day), None)
        planned_ids = set(plan["task_ids"]) if plan else set()
        planned = [t for t in self.all("task") if t["id"] in planned_ids or t.get("planned_date") == day]
        unfinished = [t["title"] for t in planned if t["status"] not in ("Done", "Blocked") or (t.get("completed_at", "")[:10] > day)]
        blocked = [t["title"] for t in planned if t["status"] == "Blocked" and t["updated_at"][:10] <= day]
        blocked.extend(e["details"].get("title", "执行异常，请核对任务") for e in events if e["type"] in ("AgentRunFailed", "AgentRunCanceled", "AgentRunInterrupted"))
        summary = "今天完成：\n" + ("\n".join(f"- {x}" for x in done) or "- 暂无")
        if decisions:
            summary += "\n\n今日决策：\n" + "\n".join(f"- {x}" for x in decisions)
        if artifact_names:
            summary += "\n\n产物：\n" + "\n".join(f"- {x}" for x in artifact_names)
        if changed_notes:
            summary += "\n\n知识库变更（仅供核对，不自动计为完成）：\n" + "\n".join(f"- {x}" for x in changed_notes[:20])
        if unfinished:
            summary += "\n\n未完成：\n" + "\n".join(f"- {x}" for x in unfinished)
        if blocked:
            summary += "\n\n阻塞与执行异常（需要处理）：\n" + "\n".join(f"- {x}" for x in dict.fromkeys(blocked))
        revisions = list(log.get("revisions", [])) if log else []
        if log:
            revisions.append({"summary": log["summary"], "saved_at": stamp()})
        item = self.put("daily_log", {"id": log["id"] if log else identifier(), "date": day, "summary": summary, "source_event_ids": [e["id"] for e in events], "confirmed_at": None, "revisions": revisions})
        self.event("DailyLogDrafted", "daily_log", item["id"], details={"date": day})
        return item

    def update_log(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("daily_log", p)
        if item.get("confirmed_at"):
            raise ValueError("日报已封存")
        item["summary"] = required_text(p.get("summary"), "日报内容", 20000)
        if self.log_view(item)["stale"]:
            if not p.get("acknowledge_events") or set(p.get("source_event_ids", [])) != {e["id"] for e in self.log_events(item["date"])}:
                raise ValueError("存在新增事件，请核对最新事件后勾选确认")
            item["source_event_ids"] = [e["id"] for e in self.log_events(item["date"])]
        item = self.put("daily_log", item)
        self.event("DailyLogEdited", "daily_log", item["id"], details={"date": item["date"]})
        return item

    def confirm_log(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("daily_log", p)
        if item.get("confirmed_at"):
            raise ValueError("日报已确认")
        if self.log_view(item)["stale"]:
            raise ValueError("日报有新增事件，请更新草稿或核对修改后再结束今天")
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

    def research_intelligence(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self.get("intelligence_item", p.get("id") or "")
        if not item:
            raise ValueError("情报不存在")
        task = self.create_task({
            "title": f"深入研究：{item['title']}",
            "description": f"来源：{item['source']}\n{item.get('url') or ''}\n\n研究原因：{item['why_recommended']}",
            "project_id": item.get("project_id"), "source": "Intelligence",
            "executor_type": "agent",
        })
        item["feedback"] = "deep_research"
        self.put("intelligence_item", item)
        self.event("IntelligenceResearchRequested", "intelligence_item", item["id"], item.get("project_id"), {"task_id": task["id"]})
        return task

    def refresh_channel(self, p: dict[str, Any]) -> dict[str, Any]:
        channel = self.get("intelligence_channel", p.get("id") or "")
        if not channel:
            raise ValueError("频道不存在")
        source_urls = [line.strip() for line in channel.get("sources", "").splitlines() if line.strip()]
        if not source_urls:
            raise ValueError("请先为频道设置 RSS/Atom 来源地址，每行一个")
        existing = self.all("intelligence_item")
        known_urls = {item.get("url") for item in existing}
        today_count = sum(1 for item in existing if item["channel_id"] == channel["id"] and item["created_at"][:10] == local_day())
        remaining = max(0, channel["daily_limit"] - today_count)
        if not remaining:
            return {"added": 0, "errors": [], "reason": "已达到今日频道上限"}
        keywords = [word.casefold() for word in re.split(r"[\s,，、;；/]+", channel.get("boundary") or "") if len(word.strip()) >= 2]
        excluded = [word.casefold() for word in re.split(r"[\n,，、;；]+", channel.get("filter_rule") or "") if word.strip()]
        added, errors = 0, []
        for url in source_urls[:20]:
            if added >= remaining:
                break
            try:
                entries = fetch_feed(url)
            except (ValueError, OSError, TimeoutError) as exc:
                errors.append({"source": url, "error": str(exc)})
                continue
            source_name = Path(url.split("/", 3)[2]).name
            for entry in entries:
                if added >= remaining:
                    break
                if entry["url"] in known_urls:
                    continue
                haystack = (entry["title"] + " " + entry["summary"]).casefold()
                if any(word in haystack for word in excluded):
                    continue
                matched = [word for word in keywords if word in haystack]
                if keywords and not matched:
                    continue
                reason = f"命中 {channel['name']} 频道边界：{', '.join(matched[:3])}" if matched else f"来自你设定的 {channel['name']} 频道来源"
                self.create_intelligence({
                    "title": entry["title"], "source": source_name, "url": entry["url"],
                    "summary": entry["summary"], "why_recommended": reason,
                    "channel_id": channel["id"], "published_at": stamp(),
                })
                known_urls.add(entry["url"])
                added += 1
        self.event("IntelligenceChannelRefreshed", "intelligence_channel", channel["id"], details={"added": added, "sources": len(source_urls)})
        return {"added": added, "errors": errors}

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
            if not destination.parent.resolve().is_relative_to(vault.resolve()):
                raise ValueError("知识写入目录必须位于 Obsidian vault 内")
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

    def _recover_interrupted_runs(self) -> None:
        for run in self.all("agent_run"):
            if run.get("status") == "Running":
                run["status"] = "Interrupted"
                run["error"] = "服务重启，无法确认外部执行结果。请检查工作目录后重试。"
                run["finished_at"] = stamp()
                self.put("agent_run", run)
                self._record_artifacts(run, run.get("before_snapshot", {}), recovered=True)
                task = self.get("task", run["task_id"])
                if task and task["status"] == "Running":
                    task["status"] = "Blocked"
                    self.put("task", task)
                self.event("AgentRunInterrupted", "agent_run", run["id"], task.get("project_id") if task else None)

    def scan_obsidian(self, p: dict[str, Any]) -> dict[str, Any]:
        day = p.get("date") or local_day()
        if day != local_day():
            raise ValueError("只能扫描今天的文件变化")
        settings = self.get("settings", "settings") or {}
        vault_path = settings.get("obsidian_vault") or ""
        if not vault_path:
            return {"configured": False, "changes": 0}
        vault = Path(vault_path)
        if not vault.is_dir():
            raise ValueError("Obsidian vault 路径不可读取")
        seen = {(event["details"].get("path"), event["details"].get("modified_at"))
                for event in self.events(day) if event["type"] == "ObsidianFileChanged"}
        count = 0
        for path in vault.rglob("*.md"):
            try:
                relative = path.relative_to(vault)
                if any(part.startswith(".") for part in relative.parts) or not path.is_file():
                    continue
                modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
                if modified.date().isoformat() != day:
                    continue
                key = (str(relative), modified.isoformat(timespec="seconds"))
                if key in seen:
                    continue
                self.event("ObsidianFileChanged", "settings", "settings", details={"path": key[0], "modified_at": key[1]})
                count += 1
            except OSError:
                continue
        return {"configured": True, "changes": count}

    def start_agent(self, p: dict[str, Any]) -> dict[str, Any]:
        if self._stopping:
            raise ValueError("服务正在关闭")
        task = self.get("task", p.get("task_id") or "")
        if not task:
            raise ValueError("任务不存在")
        if task["status"] not in ("Inbox", "Planned", "Blocked", "Review"):
            raise ValueError("当前任务不能启动 Agent")
        if not shutil.which("codex"):
            raise ValueError("本机未找到 Codex CLI")
        project = self.get("project", task.get("project_id") or "")
        workspace = Path(project.get("workspace_path") or "") if project else None
        if not workspace or not project.get("workspace_path") or not workspace.is_dir():
            raise ValueError("请先在项目设置中填写有效的本地工作目录")
        workspace = workspace.resolve()
        for active in self.all("agent_run"):
            if active["status"] == "Running" or active["id"] in self._workers:
                other = Path(active["workspace_path"]).resolve()
                if workspace.is_relative_to(other) or other.is_relative_to(workspace):
                    raise ValueError("该工作目录已有执行或正在停止的任务，请等待结束")
        instruction = (p.get("instruction") or "").strip()
        if len(instruction) > 4000:
            raise ValueError("修改要求过长")
        prompt = (
            f"任务：{task['title']}\n\n描述与完成标准：\n{task.get('description') or task['title']}\n"
            f"\n补充修改要求：\n{instruction}\n" if instruction else
            f"任务：{task['title']}\n\n描述与完成标准：\n{task.get('description') or task['title']}\n"
        )
        prompt += "\n请在指定工作目录内完成任务，最后清楚列出实际改动、验证结果和仍需人工审核的事项。"
        context = {
            "project": {"name": project["name"], "description": project.get("description", ""), "stage": project.get("stage", "")},
            "active_decisions": [{"title": d["title"], "content": d["content"]} for d in self.all("decision") if d["status"] == "Active" and d.get("project_id") in (None, project["id"])],
            "personal_rules": [r["text"] for r in self.all("personal_rule") if r["enabled"] and r["category"] in ("Agent", "General")],
        }
        prompt += "\n以下是用户明确记录的项目约束与参考规则，请遵守；若与任务矛盾请说明阻塞：\n" + json.dumps(context, ensure_ascii=False)
        before = self._workspace_snapshot(workspace)
        run = self.put("agent_run", {"task_id": task["id"], "agent_id": "Codex", "status": "Running", "started_at": stamp(), "finished_at": None, "result": "", "error": "", "workspace_path": str(workspace), "before_snapshot": before})
        task["status"] = "Running"
        task["executor_type"] = "agent"
        task["agent_id"] = "Codex"
        task["review_status"] = None
        self.put("task", task)
        self.event("AgentRunStarted", "agent_run", run["id"], task.get("project_id"), {"title": task["title"], "agent": "Codex"})
        worker = threading.Thread(target=self._run_codex, args=(run["id"], prompt, before), daemon=True)
        self._workers[run["id"]] = worker
        worker.start()
        return {k: v for k, v in run.items() if k != "before_snapshot"}

    @staticmethod
    def _workspace_snapshot(workspace: Path) -> dict[str, tuple[int, int]]:
        """Record visible workspace files so an Agent Run can show changed artifacts."""
        ignored = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
        files: dict[str, tuple[int, int]] = {}
        for root, dirs, names in os.walk(workspace):
            dirs[:] = [name for name in dirs if name not in ignored and not name.startswith(".")]
            for name in names:
                if name.startswith("."):
                    continue
                path = Path(root) / name
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    stat = path.stat()
                    files[str(path.relative_to(workspace))] = (stat.st_mtime_ns, stat.st_size)
                except OSError:
                    continue
                if len(files) >= 20000:
                    return files
        return files

    def _record_artifacts(self, run: dict[str, Any], before: dict, recovered: bool = False) -> None:
        if run.get("evidence_recorded"):
            return
        # Older runs have no baseline; never label the whole workspace as new.
        if "before_snapshot" not in run:
            run["evidence_note"] = "旧执行没有文件基线，请直接核对工作目录。"
            self.put("agent_run", run)
            return
        after = self._workspace_snapshot(Path(run["workspace_path"]))
        baseline = {name: tuple(value) for name, value in before.items()}
        task = self.get("task", run["task_id"])
        for relative in sorted(after.keys() | baseline.keys()):
            if baseline.get(relative) == after.get(relative):
                continue
            change = "Deleted" if relative not in after else "Created" if relative not in baseline else "Modified"
            artifact = self.put("artifact", {
                "task_id": run["task_id"], "agent_run_id": run["id"], "name": relative,
                "path": str(Path(run["workspace_path"]) / relative), "change": change,
                "status": "Review", "recovered": recovered,
            })
            self.event("ArtifactCreated", "artifact", artifact["id"], task.get("project_id") if task else None,
                       {"name": relative, "change": change, "recovered": recovered})
        run["evidence_recorded"] = True
        run["evidence_note"] = "重启后补采，可能包含中断后的其他改动，请核对。" if recovered else "文件元数据比较；请核对工作目录中的实际内容。"
        run.pop("before_snapshot", None)
        self.put("agent_run", run)

    def _run_codex(self, run_id: str, prompt: str, before: dict[str, tuple[int, int]]) -> None:
        with self.lock:
            run = self.get("agent_run", run_id)
        if not run or run["status"] != "Running" or self._stopping:
            with self.lock:
                if run:
                    self._record_artifacts(run, before)
                self._workers.pop(run_id, None)
            return
        output_path = self.path.parent / f"agent-{run_id}.txt"
        cmd = ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "workspace-write", "-C", run["workspace_path"], "-o", str(output_path), "-"]
        try:
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            with self.lock:
                self._processes[run_id] = process
                if self._stopping or self.get("agent_run", run_id)["status"] != "Running":
                    process.terminate()
            stdout, stderr = process.communicate(prompt, timeout=3600)
            result = output_path.read_text(encoding="utf-8") if output_path.exists() else stdout
            error = "" if process.returncode == 0 else (stderr[-4000:] or "Codex 执行失败")
            succeeded = process.returncode == 0
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            result, error, succeeded = "", "Codex 执行超时", False
        except OSError as exc:
            result, error, succeeded = "", str(exc), False
        finally:
            output_path.unlink(missing_ok=True)
        with self.lock:
            self._processes.pop(run_id, None)
            run = self.get("agent_run", run_id)
            if run:
                self._record_artifacts(run, before)
                run = self.get("agent_run", run_id)
            self._workers.pop(run_id, None)
            if not run or run["status"] != "Running":
                return
            task = self.get("task", run["task_id"])
            run["status"] = "Finished" if succeeded else "Failed"
            run["result"] = result[:30000]
            run["error"] = error
            run["finished_at"] = stamp()
            self.put("agent_run", run)
            if task:
                task["status"] = "Review" if succeeded else "Blocked"
                task["result"] = run["result"] if succeeded else ""
                task["review_status"] = "Pending" if succeeded else "Failed"
                self.put("task", task)
            self.event("AgentRunFinished" if succeeded else "AgentRunFailed", "agent_run", run_id, task.get("project_id") if task else None, {"title": task["title"] if task else "Agent Run", "status": run["status"]})

    def cancel_agent(self, p: dict[str, Any]) -> dict[str, Any]:
        run = self._existing("agent_run", p)
        if run["status"] != "Running":
            raise ValueError("Agent 当前不在运行")
        process = self._processes.get(run["id"])
        if process:
            process.terminate()
        run["status"] = "Canceled"
        run["finished_at"] = stamp()
        self.put("agent_run", run)
        task = self.get("task", run["task_id"])
        if task:
            task["status"] = "Blocked"
            self.put("task", task)
        self.event("AgentRunCanceled", "agent_run", run["id"], task.get("project_id") if task else None)
        return run

    def review_agent(self, p: dict[str, Any]) -> dict[str, Any]:
        task = self.get("task", p.get("task_id") or "")
        if not task or task["status"] != "Review":
            raise ValueError("任务不在待审核状态")
        choice = p.get("choice")
        if choice == "approve":
            task["status"] = "Done"
            task["review_status"] = "Approved"
            task["completed_at"] = stamp()
            task = self.put("task", task)
            for artifact in self.all("artifact"):
                if artifact.get("task_id") == task["id"] and artifact.get("status") == "Review":
                    artifact["status"] = "Approved"
                    self.put("artifact", artifact)
            self.event("TaskReviewed", "task", task["id"], task.get("project_id"), {"title": task["title"], "choice": choice})
            self.event("TaskCompleted", "task", task["id"], task.get("project_id"), {"title": task["title"]})
            return task
        if choice in ("revise", "rerun"):
            return self.start_agent({"task_id": task["id"], "instruction": p.get("instruction") or ""})
        raise ValueError("审核选择无效")

    def generate_brief(self, p: dict[str, Any]) -> dict[str, Any]:
        if not shutil.which("codex"):
            raise ValueError("本机未找到 Codex CLI")
        tasks = [t for t in self.all("task") if t["status"] in ("Inbox", "Planned") and not t.get("archived_at")]
        if not tasks:
            raise ValueError("先创建任务，才能生成建议")
        decisions = [d for d in self.all("decision") if d["status"] == "Active"]
        logs = sorted([log for log in self.all("daily_log") if log["date"] < local_day() and log.get("confirmed_at")], key=lambda item: item["date"], reverse=True)
        context = {
            "today": local_day(),
            "unfinished_tasks": [{"id": t["id"], "title": t["title"], "deadline": t.get("deadline"), "priority": t["priority"], "project_id": t.get("project_id")} for t in tasks[:60]],
            "projects": [{"id": x["id"], "name": x["name"], "stage": x["stage"], "pulse": x["pulse"]} for x in self.all("project")],
            "active_decisions": [{"title": x["title"], "content": x["content"]} for x in decisions[:30]],
            "yesterday_log": logs[0]["summary"] if logs else "",
            "previous_log_date": logs[0]["date"] if logs else None,
            "blocked_tasks": [{"title": t["title"], "project_id": t.get("project_id")} for t in self.all("task") if t["status"] == "Blocked" and not t.get("archived_at")],
            "intelligence": [{"title": x["title"], "why_recommended": x["why_recommended"]} for x in self.all("intelligence_item") if x.get("feedback") != "ignore"][:15],
            "personal_rules": [r["text"] for r in self.all("personal_rule") if r["enabled"]],
        }
        prompt = (
            "你是 Personal OS 的每日计划建议器。只根据提供的 JSON 上下文，从 unfinished_tasks 选择最多 3 项。"
            "尊重 active_decisions。仅输出 JSON 对象，形如 {\"priorities\":[{\"task_id\":\"原始 id\",\"reason\":\"具体原因\"}]}。"
            "不得虚构任务或完成状态。\n" + json.dumps(context, ensure_ascii=False)
        )
        raw = self._codex_readonly(prompt)
        try:
            parsed = json.loads(raw)
            proposed = parsed["priorities"]
            if not isinstance(proposed, list):
                raise ValueError("格式无效")
            task_index = {t["id"]: t for t in tasks}
            priorities = []
            for item in proposed[:3]:
                task = task_index.get(item.get("task_id"))
                if task and item["task_id"] not in [x["task_id"] for x in priorities]:
                    priorities.append({"task_id": task["id"], "title": task["title"], "reason": required_text(item.get("reason"), "建议原因", 500)})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Codex 返回的建议格式无效") from exc
        if not priorities:
            raise ValueError("Codex 没有选出有效任务")
        current = next((x for x in self.all("daily_brief") if x["date"] == local_day()), None)
        brief = self.put("daily_brief", {"id": current["id"] if current else identifier(), "date": local_day(), "priorities": priorities, "source": "Codex"})
        self.event("MorningBriefGenerated", "daily_brief", brief["id"], details={"task_ids": [x["task_id"] for x in priorities]})
        return brief

    def generate_project_pulse(self, p: dict[str, Any]) -> dict[str, Any]:
        project = self.get("project", p.get("id") or "")
        if not project:
            raise ValueError("项目不存在")
        tasks = [task for task in self.all("task") if task.get("project_id") == project["id"]]
        decisions = [decision for decision in self.all("decision") if decision.get("project_id") == project["id"] and decision["status"] == "Active"]
        events = [event for event in self.events() if event.get("project_id") == project["id"]][:30]
        context = {"project": project, "tasks": [{"title": task["title"], "status": task["status"], "deadline": task.get("deadline")} for task in tasks], "active_decisions": [{"title": d["title"], "content": d["content"]} for d in decisions], "recent_events": [{"type": e["type"], "details": e["details"]} for e in events]}
        prompt = "根据以下真实项目上下文，用中文写不超过 180 字的项目态势，包含当前阶段、进展、重点、风险。尊重已有决策，不虚构进度。只输出态势正文。\n" + json.dumps(context, ensure_ascii=False)
        pulse = required_text(self._codex_readonly(prompt), "项目态势", 2000)
        current = self.get("project", project["id"])
        if not current or current["updated_at"] != project["updated_at"]:
            raise ValueError("项目在生成期间已更新，请重新生成")
        project["pulse"] = pulse
        project["pulse_manual"] = False
        project["pulse_generated_at"] = stamp()
        project = self.put("project", project)
        self.event("ProjectPulseGenerated", "project", project["id"], project["id"])
        return project

    def summarize_log(self, p: dict[str, Any]) -> dict[str, Any]:
        log = self._existing("daily_log", p)
        if log.get("confirmed_at"):
            raise ValueError("日报已封存")
        events = self.log_events(log["date"])
        rules = [rule["text"] for rule in self.all("personal_rule") if rule["enabled"] and rule["category"] in ("Daily Log", "General")]
        context = {"date": log["date"], "events": [{"type": e["type"], "details": e["details"]} for e in events], "rules": rules, "existing_draft": log["summary"]}
        prompt = "根据真实事件写一份简洁中文日报：已完成、产物、重要决策、未完成。规则必须遵守。Obsidian 文件变化是线索，不自动算完成。不得虚构。只输出日报正文。\n" + json.dumps(context, ensure_ascii=False)
        summary = required_text(self._codex_readonly(prompt), "日报内容", 20000)
        current = self.get("daily_log", log["id"])
        if not current or current["updated_at"] != log["updated_at"] or current.get("confirmed_at"):
            raise ValueError("日报在生成期间已修改或确认，请重新生成")
        log["summary"] = summary
        log.setdefault("revisions", []).append({"summary": current["summary"], "saved_at": stamp()})
        log["source_event_ids"] = [e["id"] for e in events]
        log = self.put("daily_log", log)
        self.event("DailyLogSummarized", "daily_log", log["id"], details={"date": log["date"]})
        return log

    def _codex_readonly(self, prompt: str) -> str:
        if not shutil.which("codex"):
            raise ValueError("本机未找到 Codex CLI")
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "result.txt"
            try:
                process = subprocess.run(
                    ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only", "-C", str(self.path.parent), "-o", str(output), "-"],
                    input=prompt, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError(f"Codex 生成失败：{exc}") from exc
            if process.returncode != 0 or not output.exists():
                raise ValueError("Codex 未能返回结果，请检查运行时配置")
            return output.read_text(encoding="utf-8").strip()

    def _existing(self, kind: str, p: dict[str, Any]) -> dict[str, Any]:
        item = self.get(kind, p.get("id") or "")
        if not item:
            raise ValueError("对象不存在")
        return item
