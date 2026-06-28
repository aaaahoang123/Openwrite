from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

@dataclass(frozen=True)
class TurnInput:
    recent_messages: list[dict[str, Any]]
    pending_confirmation: dict[str, Any] | None = None
    open_questions: list[dict[str, Any]] = field(default_factory=list)
    source_sha: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TurnInput:
        return cls(
            recent_messages=data["recent_messages"],
            pending_confirmation=data.get("pending_confirmation"),
            open_questions=data.get("open_questions", []),
            source_sha=data.get("source_sha")
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class ToolEvent:
    event_type: str
    payload: dict[str, Any]
    timestamp: float | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ToolEvent:
        return cls(
            event_type=data["event_type"],
            payload=data["payload"],
            timestamp=data.get("timestamp")
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class TurnResult:
    status: Literal["successful", "blocked", "failed"]
    message: str
    data: dict[str, Any] | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TurnResult:
        return cls(
            status=data["status"],
            message=data["message"],
            data=data.get("data")
        )

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

