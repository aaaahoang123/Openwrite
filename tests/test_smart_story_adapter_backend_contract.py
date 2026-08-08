from __future__ import annotations

import json

from tools.smart_story_adapter.chat_config import ChatAdapterConfig
from tools.smart_story_adapter.runner import ChatTurnAdapterRunner


COMPLETE_CHAT_TURN_FIXTURE = json.loads(
    """
    {
      "agent_project_id": 3,
      "chat_turn_id": 2,
      "status": "succeeded",
      "assistant_message": "Chapter 5 is ready.",
      "blocked": false,
      "next_action": "done",
      "pending_confirmation": null,
      "open_questions": [],
      "changed_files": ["data/novels/100/data/manuscript/arc_001/ch_005.md"],
      "commit_sha": "new_sha",
      "output_ids": [],
      "tool_events": [
        {
          "type": "tool_call",
          "tool_name": "read_outline",
          "args": {"path": "outline.md"},
          "result": null,
          "message": "Read outline.",
          "sequence": 1
        }
      ],
      "conversation_summary": "Chapter 5 is ready.",
      "input_tokens": 1200,
      "output_tokens": 1800,
      "tool_call_count": 1,
      "failure_category": null,
      "user_message": null
    }
    """
)

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
        return COMPLETE_CHAT_TURN_FIXTURE["changed_files"]

    def commit_files(self, workspace, files, message) -> str:
        self.commits.append((files, message))
        return COMPLETE_CHAT_TURN_FIXTURE["commit_sha"]

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
        self.completed = payload
        return {"accepted": True}


def test_adapter_emits_complete_chat_turn_payload_accepted_by_backend_contract(tmp_path):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100", encoding="utf-8")

    def run_openwrite(workspace, config) -> int:
        (workspace / "turn_result.json").write_text(json.dumps(TURN_RESULT_FIXTURE), encoding="utf-8")
        (workspace / "tool_events.jsonl").write_text(
            json.dumps(COMPLETE_CHAT_TURN_FIXTURE["tool_events"][0]) + "\n",
            encoding="utf-8",
        )
        return 0

    config = ChatAdapterConfig(
        chat_session_id=1,
        chat_turn_id=COMPLETE_CHAT_TURN_FIXTURE["chat_turn_id"],
        agent_project_id=COMPLETE_CHAT_TURN_FIXTURE["agent_project_id"],
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
    assert mcp.completed == COMPLETE_CHAT_TURN_FIXTURE
