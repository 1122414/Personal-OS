"""Personal to-dos: things the user does and ticks off, separate from agent tasks.

"Today" is derived, not confirmed: unfinished to-dos planned on or before today
stay there (carried over) until ticked or moved back to the pool.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .common import local_day, required_text, stamp, synchronized

TODO_KINDS = ("todo",)
TODO_ACTIONS = ("create_todo", "update_todo", "toggle_todo", "plan_todo", "archive_todo", "delete_todo", "record_to_todo")


def _same_text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _optional(value: Any, field: str, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{field}格式无效或过长")
    return value.strip()


class TodoMixin:
    def _todo_project(self, project_id: Any) -> str | None:
        if project_id and not self.get("project", project_id):
            raise ValueError("项目不存在")
        return project_id or None

    def _home_next_matches(self, note: Any, home_next: Any) -> list[dict[str, Any]]:
        key = _same_text(home_next)
        if not isinstance(note, str) or not note or not key:
            return []
        return [t for t in self.all("todo") if t.get("home_item_note") == note and _same_text(t.get("home_next_snapshot")) == key and not t.get("archived_at")]

    def home_next_todo(self, note: Any, home_next: Any) -> dict[str, Any] | None:
        matches = self._home_next_matches(note, home_next)
        if not matches:
            return None
        pending = [t for t in matches if not t.get("done_at")]
        todo = pending[0] if pending else max(matches, key=lambda t: t["done_at"])
        return {"id": todo["id"], "done": bool(todo.get("done_at")), "planned_date": todo.get("planned_date")}

    def create_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        pending = [t for t in self._home_next_matches(p.get("home_item_note"), p.get("home_next_snapshot")) if not t.get("done_at")]
        if pending:
            return self.plan_todo({"id": pending[0]["id"], "today": True}) if p.get("today") and not pending[0].get("planned_date") else pending[0]
        record_id = p.get("record_id") or None
        if record_id and not self.get("record", record_id):
            raise ValueError("来源记录不存在")
        item = self.put("todo", {
            "title": required_text(p.get("title"), "待办", 200),
            "note": _optional(p.get("note"), "备注", 2000),
            "planned_date": local_day() if p.get("today") else None,
            "done_at": None, "archived_at": None,
            "project_id": self._todo_project(p.get("project_id")),
            "home_item_note": _optional(p.get("home_item_note"), "长线事项", 500) or None,
            "home_next_snapshot": _optional(p.get("home_next_snapshot"), "下一步", 500) or None,
            "record_id": record_id,
        })
        self.event("TodoCreated", "todo", item["id"], item["project_id"], {"title": item["title"], "today": bool(item["planned_date"])})
        return item

    def update_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("todo", p)
        if "title" in p:
            item["title"] = required_text(p["title"], "待办", 200)
        if "note" in p:
            item["note"] = _optional(p["note"], "备注", 2000)
        if "project_id" in p:
            item["project_id"] = self._todo_project(p["project_id"])
        item = self.put("todo", item)
        self.event("TodoUpdated", "todo", item["id"], item["project_id"], {"title": item["title"]})
        return item

    def toggle_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("todo", p)
        if item.get("archived_at"):
            raise ValueError("请先取消归档")
        if item.get("done_at"):
            item["done_at"] = None
            kind = "TodoReopened"
        else:
            item["done_at"] = stamp()
            kind = "TodoCompleted"
        item = self.put("todo", item)
        self.event(kind, "todo", item["id"], item.get("project_id"), {"title": item["title"]})
        return item

    def plan_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("todo", p)
        if item.get("archived_at") or item.get("done_at"):
            raise ValueError("已完成或已归档的待办不能安排")
        item["planned_date"] = local_day() if p.get("today") else None
        item = self.put("todo", item)
        self.event("TodoPlanned", "todo", item["id"], item.get("project_id"), {"title": item["title"], "today": bool(item["planned_date"])})
        return item

    def archive_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("todo", p)
        item["archived_at"] = None if p.get("restore") else stamp()
        if item["archived_at"]:
            item["planned_date"] = None
        item = self.put("todo", item)
        self.event("TodoRestored" if p.get("restore") else "TodoArchived", "todo", item["id"], item.get("project_id"), {"title": item["title"]})
        return item

    def delete_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        item = self._existing("todo", p)
        self.delete("todo", item["id"])
        self.event("TodoDeleted", "todo", item["id"], item.get("project_id"), {"title": item["title"]})
        return {"deleted": item["id"]}

    def record_to_todo(self, p: dict[str, Any]) -> dict[str, Any]:
        record = self._existing("record", p)
        if record.get("todo_id") and self.get("todo", record["todo_id"]):
            return self.get("todo", record["todo_id"])
        todo = self.create_todo({"title": p.get("title") or record["title"], "note": record["content"][:2000], "record_id": record["id"]})
        record["todo_id"] = todo["id"]
        self.put("record", record)
        return todo

    def todos_for_day(self, day: str) -> list[dict[str, Any]]:
        """To-dos that belong to ``day``: planned on or before it and not finished before it."""
        result = []
        for item in self.all("todo"):
            if item.get("archived_at") or not item.get("planned_date") and not item.get("done_at"):
                continue
            done_day = (item.get("done_at") or "")[:10]
            if done_day and done_day != day and not (item.get("planned_date") and item["planned_date"] <= day < done_day):
                continue
            if not done_day and item["planned_date"] > day:
                continue
            carried = (date.fromisoformat(day) - date.fromisoformat(item["planned_date"])).days if not done_day and item["planned_date"] < day else 0
            result.append({**item, "carried_days": carried})
        result.sort(key=lambda x: (bool(x.get("done_at")), x.get("done_at") or "", x.get("planned_date") or "", x["created_at"]))
        return result

    def today_todos(self) -> list[dict[str, Any]]:
        return self.todos_for_day(local_day())

    @synchronized
    def split_todos(self) -> int:
        """Move self-executed tasks into to-dos once; agent tasks stay tasks."""
        with_runs = {run["task_id"] for run in self.all("agent_run")}
        legacy = [task for task in self.all("task") if task.get("executor_type", "self") == "self" and task["id"] not in with_runs]
        if not legacy:
            return 0
        self.create_backup({})
        for task in legacy:
            done = task["status"] == "Done"
            todo = self.put("todo", {
                "title": task["title"][:200], "note": (task.get("description") or "")[:2000],
                "planned_date": task.get("planned_date") if task["status"] == "Planned" else None,
                "done_at": (task.get("completed_at") or task["updated_at"]) if done else None,
                "archived_at": task.get("archived_at"), "project_id": task.get("project_id"),
                "home_item_note": None, "home_next_snapshot": None,
                "record_id": task.get("record_id"), "migrated_from_task": task["id"],
            })
            if task.get("record_id"):
                record = self.get("record", task["record_id"])
                if record and record.get("task_id") == task["id"]:
                    record.update(task_id=None, todo_id=todo["id"])
                    self.put("record", record)
            self.delete("task", task["id"])
            self.event("TaskMigratedToTodo", "todo", todo["id"], todo["project_id"], {"title": todo["title"], "task_id": task["id"]})
        return len(legacy)
