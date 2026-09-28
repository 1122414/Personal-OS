"""Shared validation and timestamps for persisted workspace objects."""

import uuid
from datetime import date, datetime
from functools import wraps
from typing import Any


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
