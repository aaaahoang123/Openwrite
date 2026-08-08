from __future__ import annotations

import json

import pytest

from tools.smart_story_adapter.chat_config import ChatAdapterConfig
from tools.smart_story_adapter.runner import ChatTurnAdapterRunner

AGENT_PROJECT_ID = 3
CHAT_TURN_ID = 2
CHANGED_FILES = ["data/novels/100/data/manuscript/arc_001/ch_005.md"]
COMMIT_SHA = "new_sha"
TOOL_EVENT = {
    "type": "tool_call",
    "tool_name": "read_outline",
    "args": {"path": "outline.md"},
    "result": None,
    "message": "Read outline.",
    "sequence": 1,
}

TURN_RESULT_FIXTURE = json.loads(
    """
    {
      "status": "successful",
      "message": "Chapter 5 is ready.",
      "data": {
        "blocked": false,
        "next_action": "done",
        "pending_confirmation": null,
        "open_questions": [],
        "conversation_summary": "Chapter 5 is ready.",
        "usage": {"prompt_tokens": 1200, "completion_tokens": 1800},
        "tool_call_count": 1
      }
    }
    """
)


class ContractGitOps:
    def __init__(self) -> None:
        self.commits: list[tuple[list[str], str]] = []

    def clone_or_fetch(self, workspace, clone_url, username, password, branch) -> None:
        return None

    def verify_commit(self, workspace, sha) -> None:
        return None

    def get_changed_files(self, workspace) -> list[str]:
        return CHANGED_FILES

    def commit_files(self, workspace, files, message) -> str:
        self.commits.append((files, message))
        return COMMIT_SHA

    def push(self, workspace, branch) -> None:
        return None


class ContractMcp:
    def __init__(self) -> None:
        self.completed: dict | None = None

    def report_chat_turn_progress(self, payload: dict) -> dict:
        return {"accepted": True, **payload}

    def import_private_draft(self, payload: dict) -> dict:
        return {"private_draft_id": 78, "duplicate": False}

    def complete_chat_turn(self, payload: dict) -> dict:
        validate_complete_chat_turn_payload(payload)
        self.completed = payload
        return {"accepted": True}


REQUIRED_COMPLETE_CHAT_TURN_FIELDS = {
    "agent_project_id",
    "chat_turn_id",
    "status",
}
OPTIONAL_COMPLETE_CHAT_TURN_FIELDS = {
    "assistant_message",
    "blocked",
    "next_action",
    "pending_confirmation",
    "open_questions",
    "changed_files",
    "commit_sha",
    "output_ids",
    "tool_events",
    "conversation_summary",
    "input_tokens",
    "output_tokens",
    "tool_call_count",
    "failure_category",
    "user_message",
}
COMPLETE_CHAT_TURN_FIELD_TYPES = {
    "agent_project_id": int,
    "chat_turn_id": int,
    "assistant_message": str,
    "blocked": bool,
    "next_action": str,
    "pending_confirmation": str,
    "open_questions": list,
    "changed_files": list,
    "commit_sha": str,
    "output_ids": list,
    "tool_events": list,
    "conversation_summary": str,
    "input_tokens": int,
    "output_tokens": int,
    "tool_call_count": int,
    "failure_category": str,
    "user_message": str,
}
COMPLETE_CHAT_TURN_STRING_MAX_LENGTHS = {
    "assistant_message": 12000,
    "next_action": 120,
    "pending_confirmation": 120,
    "commit_sha": 80,
    "conversation_summary": 2000,
    "failure_category": 80,
    "user_message": 2000,
}
TERMINAL_COMPLETE_CHAT_TURN_STATUSES = {"succeeded", "failed", "cancelled"}


def validate_complete_chat_turn_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("complete_chat_turn payload must be an object")

    missing = REQUIRED_COMPLETE_CHAT_TURN_FIELDS - payload.keys()
    if missing:
        raise ValueError(f"complete_chat_turn missing required fields: {sorted(missing)}")

    # Laravel validates only declared keys and may coerce some boolean/integer values.
    # This adapter contract is intentionally stricter: outbound payloads contain only
    # declared fields and use canonical JSON bool/int types, so validate those guarantees
    # here rather than claiming Laravel rejects the broader inputs.
    permitted_fields = REQUIRED_COMPLETE_CHAT_TURN_FIELDS | OPTIONAL_COMPLETE_CHAT_TURN_FIELDS
    unexpected = set(payload) - permitted_fields
    if unexpected:
        raise ValueError(f"complete_chat_turn has unexpected fields: {sorted(unexpected)}")

    if (
        type(payload["status"]) is not str
        or payload["status"] not in TERMINAL_COMPLETE_CHAT_TURN_STATUSES
    ):
        raise ValueError("complete_chat_turn status must be terminal")

    for field, expected_type in COMPLETE_CHAT_TURN_FIELD_TYPES.items():
        value = payload.get(field)
        if field in REQUIRED_COMPLETE_CHAT_TURN_FIELDS and value is None:
            raise ValueError(f"complete_chat_turn field {field} is required")
        if value is not None and not _matches_complete_chat_turn_type(value, expected_type):
            raise ValueError(f"complete_chat_turn field {field} has an invalid type")

    for field, max_length in COMPLETE_CHAT_TURN_STRING_MAX_LENGTHS.items():
        value = payload.get(field)
        if value is not None and len(value) > max_length:
            raise ValueError(f"complete_chat_turn field {field} exceeds max length {max_length}")

    if payload["agent_project_id"] < 1 or payload["chat_turn_id"] < 1:
        raise ValueError("complete_chat_turn identifiers must be positive")

    for field in ("input_tokens", "output_tokens", "tool_call_count"):
        value = payload.get(field)
        if value is not None and value < 0:
            raise ValueError(f"complete_chat_turn field {field} must be nonnegative")


def _matches_complete_chat_turn_type(value: object, expected_type: type) -> bool:
    if expected_type in (int, bool):
        return type(value) is expected_type
    return isinstance(value, expected_type)


def valid_complete_chat_turn_payload() -> dict:
    return {
        "agent_project_id": AGENT_PROJECT_ID,
        "chat_turn_id": CHAT_TURN_ID,
        "status": "succeeded",
        "assistant_message": "Chapter 5 is ready.",
        "blocked": False,
        "next_action": "done",
        "pending_confirmation": None,
        "open_questions": [],
        "changed_files": [],
        "commit_sha": COMMIT_SHA,
        "output_ids": [],
        "tool_events": [],
        "conversation_summary": "Chapter 5 is ready.",
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_call_count": 0,
        "failure_category": None,
        "user_message": None,
    }


@pytest.mark.parametrize(
    ("case", "field", "value"),
    [
        ("missing required project id", "agent_project_id", ...),
        ("missing required turn id", "chat_turn_id", ...),
        ("missing required status", "status", ...),
        ("null required project id", "agent_project_id", None),
        ("wrong project id type", "agent_project_id", "3"),
        ("zero project id", "agent_project_id", 0),
        ("wrong turn id type", "chat_turn_id", 2.0),
        ("invalid status enum", "status", "running"),
        ("wrong assistant message type", "assistant_message", 3),
        ("wrong blocked type", "blocked", "false"),
        ("wrong next action type", "next_action", 3),
        ("wrong pending confirmation type", "pending_confirmation", 3),
        ("wrong open questions type", "open_questions", "none"),
        ("wrong changed files type", "changed_files", "none"),
        ("wrong commit sha type", "commit_sha", 3),
        ("wrong output ids type", "output_ids", "none"),
        ("wrong tool events type", "tool_events", "none"),
        ("wrong conversation summary type", "conversation_summary", 3),
        ("negative input tokens", "input_tokens", -1),
        ("negative output tokens", "output_tokens", -1),
        ("negative tool call count", "tool_call_count", -1),
        ("wrong failure category type", "failure_category", 3),
        ("wrong user message type", "user_message", 3),
        ("unknown field", "unexpected", True),
    ],
    ids=lambda case: case,
)
def test_complete_chat_turn_contract_rejects_malformed_payloads(case, field, value):
    payload = valid_complete_chat_turn_payload()
    if value is ...:
        payload.pop(field)
    else:
        payload[field] = value

    with pytest.raises(ValueError, match="complete_chat_turn"):
        ContractMcp().complete_chat_turn(payload)


@pytest.mark.parametrize("status", sorted(TERMINAL_COMPLETE_CHAT_TURN_STATUSES))
def test_complete_chat_turn_contract_accepts_each_terminal_status(status):
    payload = valid_complete_chat_turn_payload()
    payload["status"] = status

    assert ContractMcp().complete_chat_turn(payload) == {"accepted": True}


def test_complete_chat_turn_contract_allows_optional_fields_to_be_omitted():
    payload = {
        "agent_project_id": AGENT_PROJECT_ID,
        "chat_turn_id": CHAT_TURN_ID,
        "status": "succeeded",
    }

    assert ContractMcp().complete_chat_turn(payload) == {"accepted": True}


@pytest.mark.parametrize(
    ("field", "max_length"),
    [
        ("assistant_message", 12000),
        ("next_action", 120),
        ("pending_confirmation", 120),
        ("commit_sha", 80),
        ("conversation_summary", 2000),
        ("failure_category", 80),
        ("user_message", 2000),
    ],
    ids=lambda value: str(value),
)
def test_complete_chat_turn_contract_rejects_strings_over_backend_max_length(field, max_length):
    payload = valid_complete_chat_turn_payload()
    payload[field] = "x" * (max_length + 1)

    with pytest.raises(ValueError, match=f"field {field}"):
        ContractMcp().complete_chat_turn(payload)


@pytest.mark.parametrize(
    ("field", "max_length"),
    list(COMPLETE_CHAT_TURN_STRING_MAX_LENGTHS.items()),
    ids=lambda value: str(value),
)
def test_complete_chat_turn_contract_accepts_strings_at_backend_max_length(field, max_length):
    payload = valid_complete_chat_turn_payload()
    payload[field] = "x" * max_length

    assert ContractMcp().complete_chat_turn(payload) == {"accepted": True}


def test_adapter_emits_complete_chat_turn_payload_accepted_by_backend_contract(tmp_path, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100", encoding="utf-8")
    monkeypatch.setenv(
        "AGENT_TURN_PAYLOAD",
        json.dumps(
            {
                "recent_messages": [{"role": "user", "content": "Write chapter 5."}],
                "pending_confirmation": None,
                "open_questions": [],
                "source_sha": "old_sha",
            }
        ),
    )

    def run_openwrite(workspace, config) -> int:
        (workspace / "turn_result.json").write_text(
            json.dumps(TURN_RESULT_FIXTURE), encoding="utf-8"
        )
        (workspace / "tool_events.jsonl").write_text(
            json.dumps(TOOL_EVENT) + "\n",
            encoding="utf-8",
        )
        return 0

    config = ChatAdapterConfig(
        chat_session_id=1,
        chat_turn_id=CHAT_TURN_ID,
        agent_project_id=AGENT_PROJECT_ID,
        story_id=4,
        user_message_id=5,
        source_branch="main",
        source_commit_sha="old_sha",
        mcp_endpoint="http://mcp",
        mcp_token="token",
        git_clone_url="url",
        git_username="user",
        git_password="pwd",
        llm_provider="openai",
        llm_model="gpt-4",
        llm_api_key="key",
        llm_base_url=None,
        openwrite_language="en",
        workspace=str(tmp_path),
    )
    mcp = ContractMcp()

    runner = ChatTurnAdapterRunner(
        config,
        mcp=mcp,
        git_ops=ContractGitOps(),
        run_openwrite=run_openwrite,
    )

    assert runner.run() == 0
    assert mcp.completed is not None
