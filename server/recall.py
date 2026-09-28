"""Explicit, expiring personal states and explainable, bounded record recall."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .common import required_text, stamp, synchronized
from .workspace import check_version

RECALL_KINDS = ("personal_state", "idea_review")
RECALL_ACTIONS = ("create_personal_state", "update_personal_state", "confirm_personal_state", "end_personal_state", "recall_feedback")
COMMON_TERMS = {"这个", "那个", "可以", "一个", "什么", "怎么", "如何", "需要", "记录", "学习", "想法", "今天", "最近", "以后", "然后", "自己", "东西", "项目", "时候", "一下", "继续", "目前", "一些", "内容", "the", "this", "with", "from", "have", "that", "want", "learn"}


def instant(value):
    try:
        parsed = datetime.fromisoformat(value)
        if not parsed.tzinfo:
            parsed = parsed.astimezone()
        return parsed
    except (TypeError, ValueError):
        raise ValueError("时间格式无效") from None


def state_expiry(value, now):
    if value in (None, ""):
        return (now + timedelta(days=7)).isoformat()
    if not isinstance(value, str):
        raise ValueError("有效期限无效")
    if len(value) == 10:
        value += "T23:59:59"
    end = instant(value)
    if end <= now:
        raise ValueError("有效期限必须晚于现在")
    return end.isoformat()


def terms(text):
    result = {word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_+#.-]{2,}", text)}
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for size in range(2, min(len(run), 6) + 1):
            result.update(run[i:i + size] for i in range(len(run) - size + 1))
    return result - COMMON_TERMS


def shared_terms(left, right):
    matches = sorted(terms(left) & terms(right), key=lambda term: (-len(term), term))
    useful = []
    for term in matches:
        if any(term in previous for previous in useful):
            continue
        if len(term) >= 3 or len(matches) >= 2:
            useful.append(term)
        if len(useful) == 3:
            break
    return useful


class RecallMixin:
    def personal_state_view(self, state, now=None):
        now = now or datetime.now().astimezone()
        expired = instant(state["expires_at"]) <= now
        active = bool(state.get("confirmed_at") and not state.get("ended_at") and not expired)
        return {**state, "active": active, "expired": expired}

    def active_personal_states(self, now=None):
        return [view for state in self.all("personal_state") if (view := self.personal_state_view(state, now))["active"]]

    def _state_values(self, p, now):
        pace = p.get("pace", "normal")
        if pace not in ("normal", "light", "rest") or not isinstance(p.get("avoid_new_projects", False), bool):
            raise ValueError("学习量或推荐偏好无效")
        required_text(p.get("text"), "状态原话", 4000)
        if len(p["text"]) > 4000:
            raise ValueError("状态原话过长")
        return {"text": p["text"], "expires_at": state_expiry(p.get("expires_at"), now),
                "pace": pace, "avoid_new_projects": p.get("avoid_new_projects", False)}

    def create_personal_state(self, p):
        now = datetime.now().astimezone()
        values = self._state_values(p, now)
        source_kind = p.get("source_kind", "explicit")
        if source_kind not in ("explicit", "inference"):
            raise ValueError("状态来源无效")
        record = self._existing("record", {"id": p["record_id"]}) if p.get("record_id") else None
        if record and record["content"] != values["text"]:
            raise ValueError("状态原话与来源记录不一致，请修改记录或另建一条状态")
        if not record:
            record = self.create_record({"content": values["text"], "record_type": "status"})
        state = self.put("personal_state", {**values, "record_id": record["id"], "source_kind": source_kind,
                                           "confirmed_at": stamp() if source_kind == "explicit" else None,
                                           "ended_at": None, "original_text": values["text"]})
        self.event("PersonalStateCreated", "record", record["id"], details={"confirmed": source_kind == "explicit"})
        return state

    def update_personal_state(self, p):
        state = self._existing("personal_state", p)
        check_version(state, p)
        values = self._state_values({**state, **p}, datetime.now().astimezone())
        if values["text"] != state["text"]:
            record = self.create_record({"content": values["text"], "record_type": "status"})
            state.setdefault("previous_record_ids", []).append(state["record_id"])
            state["record_id"] = record["id"]
        state.update(values)
        return self.put("personal_state", state)

    def confirm_personal_state(self, p):
        state = self._existing("personal_state", p)
        check_version(state, p)
        if state.get("ended_at") or instant(state["expires_at"]) <= datetime.now().astimezone():
            raise ValueError("状态已结束或过期，请另记当前状态")
        state["confirmed_at"] = stamp()
        return self.put("personal_state", state)

    def end_personal_state(self, p):
        state = self._existing("personal_state", p)
        check_version(state, p)
        state["ended_at"] = stamp()
        return self.put("personal_state", state)

    def learning_state_context(self):
        states = self.active_personal_states()
        pace = "rest" if any(s["pace"] == "rest" for s in states) else "light" if any(s["pace"] == "light" for s in states) else "normal"
        return {"states": [{"text": s["text"], "source_record_id": s["record_id"], "expires_at": s["expires_at"]} for s in states],
                "pace": pace, "avoid_new_projects": any(s["avoid_new_projects"] for s in states),
                "instruction": "只按用户已确认且未过期的状态调整新建议：light 小段推进，rest 允许停止或只做极小一步；不要改动已确认计划。没有活动记录不代表缺乏动力。"}

    def _recall_allowed(self, record, now):
        if record.get("record_type") == "status" or record.get("recall_policy") == "never":
            return False
        if record.get("defer_until") and instant(record["defer_until"]) > now:
            return False
        if any(state["avoid_new_projects"] for state in self.active_personal_states(now)):
            if record.get("idea_scope") == "new_project":
                return False
            linked = any(record["id"] in topic["record_ids"] for topic in self.all("learning_topic"))
            if record.get("idea_scope") != "existing" and not linked:
                return False
        return True

    def _topic_recall_text(self, topic):
        text = topic["title"] + "\n" + topic["goal"]
        messages = [m for m in self.all("learning_message") if m["topic_id"] == topic["id"] and m["role"] == "user"][:5]
        return text + "\n" + "\n".join(message["content"][:1500] for message in messages)

    @synchronized
    def related_records(self, topic_id, now=None, limit=3):
        now = now or datetime.now().astimezone()
        topic = self._existing("learning_topic", {"id": topic_id})
        context = self._topic_recall_text(topic)
        results = []
        for record in self.all("record"):
            if record["id"] in topic["record_ids"] or not self._recall_allowed(record, now) or now - instant(record["created_at"]) < timedelta(days=1):
                continue
            matches = shared_terms(context, record["title"] + "\n" + record["content"][:12000])
            if not matches:
                continue
            reason = f"这个主题和旧记录都提到“{'、'.join(matches)}”，可以对照原文继续思考。"
            results.append({"record_id": record["id"], "record_revision": record["revision"], "topic_id": topic_id,
                            "reason": reason, "matched_terms": matches, "score": sum(len(term) for term in matches)})
        ordered = sorted(results, key=lambda item: (-item["score"], item["record_id"]))
        return ordered[:limit] if limit is not None else ordered

    @synchronized
    def recall_tick(self, now=None):
        if self._stopping:
            return
        now = now or datetime.now().astimezone()
        year, week, _ = now.isocalendar()
        key = f"{year}-W{week:02d}"
        existing = next((review for review in self.all("idea_review") if review["week"] == key), None)
        if existing:
            return existing
        candidates = {}
        for topic in self.all("learning_topic"):
            if now - instant(topic.get("last_activity_at", topic["updated_at"])) > timedelta(days=30):
                continue
            for item in self.related_records(topic["id"], now, limit=None):
                record = self.get("record", item["record_id"])
                if record["record_type"] not in ("note", "idea") or now - instant(record["created_at"]) < timedelta(days=7):
                    continue
                if record.get("last_recalled_at") and now - instant(record["last_recalled_at"]) < timedelta(days=28):
                    continue
                if item["record_id"] not in candidates or candidates[item["record_id"]]["score"] < item["score"]:
                    candidates[item["record_id"]] = {**item, "status": "Pending"}
        items = sorted(candidates.values(), key=lambda item: (-item["score"], item["record_id"]))[:3]
        return self.put("idea_review", {"week": key, "items": items, "generated_at": now.isoformat()})

    def weekly_review_view(self, now=None):
        now = now or datetime.now().astimezone()
        year, week, _ = now.isocalendar()
        key = f"{year}-W{week:02d}"
        review = next((item for item in self.all("idea_review") if item["week"] == key), None)
        if not review:
            return None
        items = []
        for item in review["items"]:
            record = self.get("record", item["record_id"])
            topic = self.get("learning_topic", item["topic_id"])
            if not record or not topic or item["status"] != "Pending" or not self._recall_allowed(record, now):
                continue
            matches = shared_terms(self._topic_recall_text(topic), record["title"] + "\n" + record["content"][:12000])
            if not set(item["matched_terms"]).intersection(matches):
                continue
            items.append({**item, "matched_terms": matches,
                          "reason": f"这个主题和旧记录都提到“{'、'.join(matches)}”，可以对照原文继续思考。",
                          "record": record, "topic_title": topic["title"]})
        return {**review, "items": items}

    def recall_feedback(self, p):
        record = self._existing("record", p)
        choice = p.get("choice")
        if choice not in ("continue", "defer", "never"):
            raise ValueError("回顾反馈无效")
        now = datetime.now().astimezone()
        if choice == "never":
            record["recall_policy"] = "never"
        elif choice == "defer":
            record["defer_until"] = (now + timedelta(days=7)).isoformat()
        else:
            record["last_recalled_at"] = now.isoformat()
            record["defer_until"] = None
        self.put("record", record)
        for review in self.all("idea_review"):
            changed = False
            for item in review["items"]:
                if item["record_id"] == record["id"] and item["status"] == "Pending":
                    item["status"] = {"continue": "Continued", "defer": "Deferred", "never": "Dismissed"}[choice]
                    changed = True
            if changed:
                self.put("idea_review", review)
        return {"record_id": record["id"], "message": {"continue": "已打开原记录，由你决定如何继续", "defer": "已搁置 7 天", "never": "这条记录不再主动推荐，原文仍保留"}[choice]}
