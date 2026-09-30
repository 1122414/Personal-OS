"""Learning cards: hand-written or pushed daily by an agent, reviewed on a fixed ladder."""

from __future__ import annotations

import json
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .common import identifier, local_day, required_text, stamp
from .runtime import RUNTIMES

CARD_KINDS = ("learning_card",)
CARD_ACTIONS = ("create_card", "update_card", "delete_card", "review_card", "restore_card", "set_card_push", "generate_cards")
INTERVALS = (7, 14, 30)
RATINGS = ("forgot", "fuzzy", "remembered")
REVIEW_HISTORY = 50
NOTE_FOLDER = "学习卡片"


def _card_text(p: dict[str, Any]) -> tuple[str, str]:
    front = required_text(p.get("front"), "卡片正面", 500)
    back = p.get("back") or ""
    if not isinstance(back, str) or len(back) > 4000:
        raise ValueError("卡片背面格式无效或过长")
    return front, back.strip()


def _same_front(text: str) -> str:
    return "".join(text.split()).lower()


def parse_cards(text: str, limit: int) -> list[dict[str, str]]:
    """Agents are asked for a bare JSON array; tolerate prose or code fences around it."""
    start, end = text.find("["), text.rfind("]")
    try:
        items = json.loads(text[start:end + 1]) if start >= 0 and end > start else None
    except ValueError:
        items = None
    if not isinstance(items, list):
        raise ValueError("生成结果不是卡片列表，未保存")
    cards = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("front"), str) and item["front"].strip():
            back = item.get("back") if isinstance(item.get("back"), str) else ""
            cards.append({"front": item["front"].strip()[:500], "back": back.strip()[:4000]})
    if not cards:
        raise ValueError("生成结果里没有可用的卡片，未保存")
    return cards[:limit]


class CardsMixin:
    def _topic_cards(self, topic_id: str) -> list[dict[str, Any]]:
        return [card for card in self.all("learning_card") if card["topic_id"] == topic_id]

    def _new_card(self, topic: dict[str, Any], front: str, back: str, source: str, engine: str | None = None) -> dict[str, Any]:
        return self.put("learning_card", {
            "topic_id": topic["id"], "front": front, "back": back, "source": source, "engine": engine,
            "step": 0, "due_date": local_day(), "last_rating": None, "reviews": [], "mastered_at": None,
        })

    def create_card(self, p: dict[str, Any]) -> dict[str, Any]:
        topic = self._existing("learning_topic", {"id": p.get("topic_id")})
        card = self._new_card(topic, *_card_text(p), "user")
        self.event("LearningCardCreated", "learning_card", card["id"], details={"topic_id": topic["id"], "front": card["front"][:80]})
        self._refresh_card_note(card["created_at"][:10])
        return card

    def update_card(self, p: dict[str, Any]) -> dict[str, Any]:
        card = self._existing("learning_card", p)
        card["front"], card["back"] = _card_text(p)
        card = self.put("learning_card", card)
        self._refresh_card_note(card["created_at"][:10])
        return card

    def delete_card(self, p: dict[str, Any]) -> dict[str, Any]:
        card = self._existing("learning_card", p)
        self.delete("learning_card", card["id"])
        self.event("LearningCardDeleted", "learning_card", card["id"], details={"topic_id": card["topic_id"], "front": card["front"][:80]})
        self._refresh_card_note(card["created_at"][:10])
        return {"deleted": card["id"]}

    def review_card(self, p: dict[str, Any]) -> dict[str, Any]:
        card = self._existing("learning_card", p)
        rating = p.get("rating")
        if rating not in RATINGS:
            raise ValueError("复习结果无效")
        if card.get("mastered_at"):
            raise ValueError("已掌握的卡片请先恢复")
        today = date.fromisoformat(local_day())
        if rating == "forgot":
            card["step"], card["due_date"] = 0, (today + timedelta(days=1)).isoformat()
        elif rating == "fuzzy":
            card["due_date"] = (today + timedelta(days=3)).isoformat()
        elif card["step"] >= len(INTERVALS):
            card["mastered_at"], card["due_date"] = stamp(), None
        else:
            card["step"] += 1
            card["due_date"] = (today + timedelta(days=INTERVALS[card["step"] - 1])).isoformat()
        card["last_rating"] = rating
        card["reviews"] = [*card["reviews"], {"at": stamp(), "rating": rating}][-REVIEW_HISTORY:]
        card = self.put("learning_card", card)
        self.event("LearningCardReviewed", "learning_card", card["id"], details={"topic_id": card["topic_id"], "rating": rating})
        return card

    def restore_card(self, p: dict[str, Any]) -> dict[str, Any]:
        card = self._existing("learning_card", p)
        card.update(mastered_at=None, step=0, due_date=(date.fromisoformat(local_day()) + timedelta(days=1)).isoformat())
        return self.put("learning_card", card)

    def set_card_push(self, p: dict[str, Any]) -> dict[str, Any]:
        topic = self._existing("learning_topic", p)
        if "push_enabled" in p:
            topic["push_enabled"] = bool(p["push_enabled"])
        if "daily_count" in p:
            count = p["daily_count"]
            if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 10:
                raise ValueError("每天张数需在 1～10 之间")
            topic["daily_count"] = count
        if "card_engine" in p:
            runtime = RUNTIMES.get(p["card_engine"])
            if not runtime or runtime.remote:
                raise ValueError("该通道不能生成学习卡片")
            topic["card_engine"] = runtime.id
        return self.put("learning_topic", topic)

    def _card_prompt(self, topic: dict[str, Any], count: int) -> str:
        fronts = [card["front"] for card in sorted(self._topic_cards(topic["id"]), key=lambda c: c["created_at"], reverse=True)[:100]]
        existing = "\n".join(f"- {front[:120]}" for front in fronts) or "（还没有卡片）"
        return (f"你在为学习主题「{topic['title']}」出今天的学习卡片。学习目标：{topic.get('goal') or '未填写，按主题标题理解'}。\n"
                f"请出 {count} 张新卡片，每张一个知识点：front 是一个具体的问题或概念（不超过 80 字），"
                "back 是准确、简洁的解答（不超过 400 字，可用 Markdown，必要时给一个小例子）。\n"
                f"不要和下面这些已有卡片重复：\n{existing}\n"
                "不要读写任何文件，不要运行命令。只输出一个 JSON 数组，例如 "
                '[{"front": "问题", "back": "解答"}]，不要输出其他文字。')

    def _generate_text(self, engine: str, prompt: str) -> str:
        runtime = RUNTIMES.get(engine)
        if not runtime or runtime.remote:
            raise ValueError("该通道不能生成学习卡片")
        executable = runtime.command_path(self._settings())
        if not executable:
            raise ValueError(f"本机未找到 {runtime.label} 命令行")
        key = f"cards-{identifier()}"
        with tempfile.TemporaryDirectory(prefix="personal-os-cards-") as temp:
            def started(process: Any) -> None:
                with self.lock:
                    self._processes[key] = process
            try:
                outcome = runtime.run(executable, prompt, Path(temp), started, lambda _: None, self._settings())
            finally:
                with self.lock:
                    self._processes.pop(key, None)
        if not outcome.succeeded:
            raise ValueError(f"{runtime.label} 生成失败：{(outcome.error or '').strip()[:300]}")
        return outcome.result

    def generate_cards(self, p: dict[str, Any]) -> dict[str, Any]:
        """Runs outside the store lock: the agent call can take minutes."""
        topic = self._existing("learning_topic", {"id": p.get("topic_id")})
        engine = topic.get("card_engine") or "codex"
        count = topic.get("daily_count") or 3
        daily = bool(p.get("daily"))

        def finish(**fields: Any) -> dict[str, Any]:
            current = self.get("learning_topic", topic["id"])
            if daily:
                fields["last_push_date"] = local_day()
            return self.put("learning_topic", {**current, **fields}) if current else topic

        try:
            cards = parse_cards(self._generate_text(engine, self._card_prompt(topic, count)), count)
        except ValueError as exc:
            with self.lock:
                if not self._stopping:
                    finish(last_push_error=str(exc)[:400])
                    self.event("LearningCardsFailed", "learning_topic", topic["id"], details={"error": str(exc)[:200]})
            raise
        label = RUNTIMES[engine].label
        with self.lock:
            if self._stopping:
                raise ValueError("服务正在关闭，生成结果未写入")
            known = {_same_front(card["front"]) for card in self._topic_cards(topic["id"])}
            saved = []
            for card in cards:
                if _same_front(card["front"]) not in known:
                    known.add(_same_front(card["front"]))
                    saved.append(self._new_card(topic, card["front"], card["back"], "ai", label))
            finish(last_push_error=None)
            self.event("LearningCardsGenerated", "learning_topic", topic["id"], details={"count": len(saved), "engine": label})
            self._refresh_card_note(local_day())
        return {"cards": saved, "message": f"{label} 生成了 {len(saved)} 张卡片"}

    def daily_card_push(self) -> None:
        for topic in self.all("learning_topic"):
            if topic.get("push_enabled") and topic.get("last_push_date") != local_day():
                try:
                    self.action("generate_cards", {"topic_id": topic["id"], "daily": True})
                except ValueError:
                    pass

    def _refresh_card_note(self, day: str) -> None:
        """Rewrite the day's Obsidian note from Personal OS, which stays the source of truth."""
        vault = self._settings().get("obsidian_vault")
        if not vault or not Path(vault).is_dir():
            return
        folder = Path(vault).resolve() / NOTE_FOLDER
        if folder.is_symlink():
            return
        note = folder / f"{day}.md"
        topics = {topic["id"]: topic["title"] for topic in self.all("learning_topic")}
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for card in sorted(self.all("learning_card"), key=lambda c: c["created_at"]):
            if card["created_at"][:10] == day:
                grouped[topics.get(card["topic_id"], "未命名主题")].append(card)
        try:
            if not grouped:
                if note.is_file() and not note.is_symlink():
                    note.unlink()
                return
            folder.mkdir(exist_ok=True)
            text = f"# 学习卡片 · {day}\n\n"
            for title, cards in grouped.items():
                text += f"## {title}\n\n" + "".join(f"### {card['front']}\n\n{card['back']}\n\n" for card in cards)
            text += "---\n由 Personal OS 生成；当天卡片有变化时整份重写，修改请在 Personal OS 中进行。\n"
            temporary = folder / f".{day}.md.tmp"
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(note)
        except OSError:
            pass
