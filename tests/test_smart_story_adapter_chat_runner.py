import json
import subprocess

import pytest

from tools.smart_story_adapter.chat_config import ChatAdapterConfig
from tools.smart_story_adapter.config import AdapterError
from tools.smart_story_adapter.runner import ChatTurnAdapterRunner, default_run_chat_openwrite


class MockGitOps:
    def __init__(self, conflict=False):
        self.cloned = False
        self.verified_sha = None
        self.pushed = False
        self.commits = []
        self.conflict = conflict
        self.changed_files = []

    def clone_or_fetch(self, workspace, clone_url, username, password, branch):
        self.cloned = True

    def verify_commit(self, workspace, sha):
        self.verified_sha = sha

    def get_changed_files(self, workspace):
        return self.changed_files

    def commit_files(self, workspace, files, message):
        self.commits.append((files, message))
        return "new_sha"

    def push(self, workspace, branch):
        if self.conflict:
            raise AdapterError("non-fast-forward", "git_conflict", "Nhánh truyện đã thay đổi")
        self.pushed = True


class MockMcpClient:
    def __init__(self, input_data=None, fail_complete=0):
        self.input_data = input_data or {"recent_messages": []}
        self.progress_calls = []
        self.imported_drafts = []
        self.completed = None
        self.fail_complete = fail_complete
        self.complete_attempts = 0

    def get_chat_turn_input(self, payload):
        return self.input_data

    def report_chat_turn_progress(self, payload):
        self.progress_calls.append(payload["status"])

    def import_private_draft(self, payload):
        self.imported_drafts.append(payload)
        return {"private_draft_id": 123}

    def complete_chat_turn(self, payload):
        self.complete_attempts += 1
        if self.complete_attempts <= self.fail_complete:
            raise Exception("Network error")
        self.completed = payload


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AGENT_TURN_PAYLOAD",
        '{"recent_messages":[{"role":"user","content":"hello"}],"pending_confirmation":null,"open_questions":[],"source_sha":"old_sha"}',
    )
    return ChatAdapterConfig(
        chat_session_id=1,
        chat_turn_id=2,
        agent_project_id=3,
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
        workspace=str(tmp_path)
    )

def test_runner_happy_path(tmp_path, config, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    
    monkeypatch.setenv("AGENT_TURN_PAYLOAD", '{"recent_messages": []}')
    
    # Mock openwrite run
    run_args = []
    def mock_run(workspace, cfg):
        run_args.append((workspace, cfg))
        (workspace / "turn_result.json").write_text(json.dumps({
            "status": "successful",
            "message": "done",
            "data": {}
        }))
        # create a draft
        draft_dir = workspace / "data" / "novels" / "100" / "data" / "manuscript"
        draft_dir.mkdir(parents=True, exist_ok=True)
        (draft_dir / "ch_1.md").write_text("# Title\ncontent")
        return 0

    git = MockGitOps()
    git.changed_files = ["novel_config.yaml", "turn_input.json", "tool_events.jsonl"]
    mcp = MockMcpClient()
    runner = ChatTurnAdapterRunner(config, mcp=mcp, git_ops=git, run_openwrite=mock_run)

    # Need monkeypatch to not sleep during retry
    monkeypatch.setattr("time.sleep", lambda x: None)

    code = runner.run()
    assert code == 0

    assert (tmp_path / "turn_input.json").read_text() == '{"recent_messages": []}'

    # check durable paths (only novel_config.yaml)
    assert len(git.commits) == 1
    assert git.commits[0][0] == ["novel_config.yaml"]
    assert git.pushed

    # progress calls
    assert mcp.progress_calls == ["started", "running", "submitting"]

    # drafts imported before completion
    assert len(mcp.imported_drafts) == 1
    assert mcp.imported_drafts[0]["content"] == "# Title\ncontent"
    
    assert mcp.completed is not None
    assert mcp.completed["status"] == "succeeded"
    assert mcp.completed["assistant_message"] == "done"
    assert mcp.completed["commit_sha"] == "new_sha"


def test_runner_fails_when_turn_payload_is_missing(tmp_path, config, monkeypatch, capsys):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    monkeypatch.delenv("AGENT_TURN_PAYLOAD", raising=False)

    def unexpected_openwrite_run(workspace, cfg):
        raise AssertionError("OpenWrite must not run without a turn payload")

    mcp = MockMcpClient()
    runner = ChatTurnAdapterRunner(
        config,
        mcp=mcp,
        git_ops=MockGitOps(),
        run_openwrite=unexpected_openwrite_run,
    )

    code = runner.run()

    assert code == 1
    assert mcp.completed is not None
    assert mcp.completed["failure_category"] == "configuration_missing"
    assert "AGENT_TURN_PAYLOAD" in capsys.readouterr().err


def test_question_only_makes_no_commit(tmp_path, config, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    
    def mock_run(workspace, cfg):
        (workspace / "turn_result.json").write_text(json.dumps({
            "status": "blocked",
            "message": "need input",
            "data": {}
        }))
        state_path = workspace / "data" / "novels" / "100" / "data" / "workflows" / "book_state.yaml"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("pending_confirmation: outline_scope\n", encoding="utf-8")
        return 0

    git = MockGitOps()
    git.changed_files = ["data/novels/100/data/workflows/book_state.yaml"]
    mcp = MockMcpClient()
    runner = ChatTurnAdapterRunner(config, mcp=mcp, git_ops=git, run_openwrite=mock_run)
    monkeypatch.setattr("time.sleep", lambda x: None)

    code = runner.run()
    assert code == 0
    assert len(git.commits) == 0
    assert not git.pushed
    
    assert mcp.completed is not None
    assert mcp.completed["status"] == "succeeded"
    assert mcp.completed["blocked"] is True
    assert mcp.completed["changed_files"] == []
    assert mcp.completed["commit_sha"] == "old_sha" # fallbacks to old sha


def test_runner_maps_nested_blocked_turn_data_without_committing_durable_files(
    tmp_path, config, monkeypatch
):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")

    def mock_run(workspace, cfg):
        (workspace / "turn_result.json").write_text(
            json.dumps(
                {
                    "status": "blocked",
                    "message": "Need confirmation.",
                    "data": {
                        "blocked": True,
                        "next_action": "confirm_outline_scope",
                        "pending_confirmation": "outline_scope",
                        "open_questions": [
                            "Which point of view should lead the chapter?"
                        ],
                        "conversation_summary": "Waiting for outline scope confirmation.",
                        "tool_call_count": 2,
                    },
                }
            )
        )
        state_path = (
            workspace
            / "data"
            / "novels"
            / "100"
            / "data"
            / "workflows"
            / "book_state.yaml"
        )
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("pending_confirmation: outline_scope\n", encoding="utf-8")
        return 0

    git = MockGitOps()
    git.changed_files = ["data/novels/100/data/workflows/book_state.yaml"]
    mcp = MockMcpClient()
    runner = ChatTurnAdapterRunner(
        config, mcp=mcp, git_ops=git, run_openwrite=mock_run
    )
    monkeypatch.setattr("time.sleep", lambda x: None)

    assert runner.run() == 0
    assert not git.commits
    assert not git.pushed
    assert mcp.completed == {
        "agent_project_id": 3,
        "chat_turn_id": 2,
        "status": "succeeded",
        "assistant_message": "Need confirmation.",
        "blocked": True,
        "next_action": "confirm_outline_scope",
        "pending_confirmation": "outline_scope",
        "open_questions": ["Which point of view should lead the chapter?"],
        "changed_files": [],
        "commit_sha": "old_sha",
        "output_ids": [],
        "tool_events": [],
        "conversation_summary": "Waiting for outline scope confirmation.",
        "input_tokens": None,
        "output_tokens": None,
        "tool_call_count": 2,
        "failure_category": None,
        "user_message": None,
    }


def test_git_conflict(tmp_path, config, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    
    def mock_run(workspace, cfg):
        (workspace / "turn_result.json").write_text(json.dumps({
            "status": "successful",
            "message": "done",
            "data": {}
        }))
        return 0

    git = MockGitOps(conflict=True)
    git.changed_files = ["novel_config.yaml"]
    mcp = MockMcpClient()
    runner = ChatTurnAdapterRunner(config, mcp=mcp, git_ops=git, run_openwrite=mock_run)
    monkeypatch.setattr("time.sleep", lambda x: None)

    code = runner.run()
    assert code == 1
    assert mcp.completed is not None
    assert mcp.completed["status"] == "failed"
    assert mcp.completed["failure_category"] == "git_conflict"


def test_mcp_retry(tmp_path, config, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    
    def mock_run(workspace, cfg):
        (workspace / "turn_result.json").write_text(json.dumps({
            "status": "successful",
            "message": "done",
            "data": {}
        }))
        return 0

    git = MockGitOps()
    git.changed_files = []
    # Fail 2 times, succeed on 3rd
    mcp = MockMcpClient(fail_complete=2)
    runner = ChatTurnAdapterRunner(config, mcp=mcp, git_ops=git, run_openwrite=mock_run)
    monkeypatch.setattr("time.sleep", lambda x: None)

    code = runner.run()
    assert code == 0
    assert mcp.complete_attempts == 3
    assert mcp.completed is not None

def test_mcp_retry_fail(tmp_path, config, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    
    def mock_run(workspace, cfg):
        (workspace / "turn_result.json").write_text(json.dumps({
            "status": "successful",
            "message": "done",
            "data": {}
        }))
        return 0

    git = MockGitOps()
    # Fail 4 times (meaning it never succeeds)
    mcp = MockMcpClient(fail_complete=4)
    runner = ChatTurnAdapterRunner(config, mcp=mcp, git_ops=git, run_openwrite=mock_run)
    monkeypatch.setattr("time.sleep", lambda x: None)

    code = runner.run()
    assert code == 1

def test_default_run_chat_openwrite(tmp_path, config, monkeypatch):
    calls = []
    class FakeProcess:
        returncode = 42

    def fake_subprocess_run(args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    code = default_run_chat_openwrite(tmp_path, config)
    assert code == 42
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ["openwrite", "chat-turn", "--in", "turn_input.json"]
    assert kwargs["cwd"] == tmp_path
    assert "LLM_PROVIDER" in kwargs["env"]
    assert kwargs["env"]["LLM_PROVIDER"] == "openai"
