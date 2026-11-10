from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class PipelineCancelled(Exception):
    pass


class EventType(str, Enum):
    DECISION = "decision"
    SEARCH = "search"
    MATRIX_CELL = "matrix_cell"
    AUDIT = "audit"
    DONE = "done"
    ERROR = "error"


@dataclass
class Event:
    type: EventType
    stage: str
    title: str
    detail: Any = None
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "stage": self.stage,
            "title": self.title,
            "detail": self.detail,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


def decision(stage: str, title: str, detail: Any = None, reason: str = "") -> Event:
    return Event(EventType.DECISION, stage, title, detail, reason)


def search_event(stage: str, title: str, detail: Any = None) -> Event:
    return Event(EventType.SEARCH, stage, title, detail)


def matrix_cell(stage: str, title: str, detail: Any = None) -> Event:
    return Event(EventType.MATRIX_CELL, stage, title, detail)


def audit_event(stage: str, title: str, detail: Any = None) -> Event:
    return Event(EventType.AUDIT, stage, title, detail)


def done_event(title: str, detail: Any = None) -> Event:
    return Event(EventType.DONE, "done", title, detail)


def error_event(title: str, detail: Any = None) -> Event:
    return Event(EventType.ERROR, "error", title, detail)