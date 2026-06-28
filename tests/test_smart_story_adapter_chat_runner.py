import json
import pytest
from pathlib import Path
from tools.smart_story_adapter.chat_config import ChatAdapterConfig
from tools.smart_story_adapter.runner import ChatTurnAdapterRunner
from tools.smart_story_adapter.config import AdapterError
import subprocess

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
def config(tmp_path):
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

    # adapter invokes openwrite chat-turn --in turn_input.json
    # We mocked run_openwrite, but let's check default_run_chat_openwrite is used properly normally or we check if the file is written
    assert (tmp_path / "turn_input.json").exists()

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
    assert mcp.completed["status"] == "successful"
    assert mcp.completed["commit_sha"] == "new_sha"


def test_question_only_makes_no_commit(tmp_path, config, monkeypatch):
    (tmp_path / "novel_config.yaml").write_text("novel_id: 100")
    
    def mock_run(workspace, cfg):
        (workspace / "turn_result.json").write_text(json.dumps({
            "status": "blocked",
            "message": "need input",
            "data": {}
        }))
        return 0

    git = MockGitOps()
    git.changed_files = ["turn_result.json"] # not durable
    mcp = MockMcpClient()
    runner = ChatTurnAdapterRunner(config, mcp=mcp, git_ops=git, run_openwrite=mock_run)
    monkeypatch.setattr("time.sleep", lambda x: None)

    code = runner.run()
    assert code == 0
    assert len(git.commits) == 0
    assert not git.pushed
    
    assert mcp.completed is not None
    assert mcp.completed["status"] == "blocked"
    assert mcp.completed["commit_sha"] == "old_sha" # fallbacks to old sha


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
    assert mcp.completed["data"]["failure_category"] == "git_conflict"


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

