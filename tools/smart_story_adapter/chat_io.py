from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class TurnInput:
    recent_messages: List[Dict[str, Any]]
    pending_confirmation: Optional[Dict[str, Any]] = None
    open_questions: List[Dict[str, Any]] = field(default_factory=list)
    source_sha: Optional[str] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "TurnInput":
        return cls(
            recent_messages=data.get("recent_messages", []),
            pending_confirmation=data.get("pending_confirmation"),
            open_questions=data.get("open_questions", []),
            source_sha=data.get("source_sha")
        )

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class ToolEvent:
    event_type: str
    payload: Dict[str, Any]
    timestamp: Optional[float] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "ToolEvent":
        return cls(
            event_type=data["event_type"],
            payload=data["payload"],
            timestamp=data.get("timestamp")
        )

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class TurnResult:
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "TurnResult":
        return cls(
            status=data["status"],
            message=data["message"],
            data=data.get("data")
        )

    def to_json(self) -> Dict[str, Any]:
        return asdict(self)
