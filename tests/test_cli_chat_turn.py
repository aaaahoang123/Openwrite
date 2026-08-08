import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import tools.cli as cli_module
import tools.web_chat_turn as wct

def test_chat_turn_command_dispatches_correctly(tmp_path, monkeypatch):
    calls = []
    
    def fake_run_chat_turn(input_path, project_root):
        calls.append((input_path, project_root))
        result = {
            "status": "successful",
            "message": "Hello",
            "data": {
                "open_questions": [],
                "changed_files": [],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}
            }
        }
        (project_root / "turn_result.json").write_text(json.dumps(result))
        return 0
    
    monkeypatch.setattr(wct, "run_chat_turn", fake_run_chat_turn)
    
    in_file = tmp_path / "turn_input.json"
    in_file.write_text("{}")
    
    monkeypatch.setattr(cli_module.Path, "cwd", lambda: tmp_path)
    
    # We can test parsing directly if needed, but for _dispatch testing SimpleNamespace is fine
    args = SimpleNamespace(command="chat-turn", in_file=str(in_file))
    
    res = cli_module._dispatch(args)
    
    assert res == 0
    assert len(calls) == 1
    assert calls[0][0] == Path(str(in_file))
    
    res_file = tmp_path / "turn_result.json"
    assert res_file.exists()
    
    data = json.loads(res_file.read_text())
    assert "status" in data
    assert "message" in data
    assert "data" in data
    
    payload = data.get("data") or {}
    assert "open_questions" in payload
    assert "changed_files" in payload
    assert "usage" in payload

def test_chat_turn_integration(tmp_path, monkeypatch):
    import tools.web_chat_turn as wct
    from tools.agent.orchestrator import OrchestratorResult
    
    in_file = tmp_path / "turn_input.json"
    in_file.write_text(json.dumps({
        "recent_messages": [
            {"role": "user", "content": "hello"}
        ]
    }))
    
    # Mock orchestrator to not actually call LLM
    class FakeOrchestrator:
        def __init__(self, *args, **kwargs):
            pass
        def handle_user_message(self, text):
            return OrchestratorResult(
                message="Mock response",
                stage=None,
                blocked=False,
                next_action="none"
            )
            
    monkeypatch.setattr(wct, "OpenWriteOrchestrator", FakeOrchestrator)
    
    res = wct.run_chat_turn(in_file, tmp_path)
    
    assert res == 0
    res_file = tmp_path / "turn_result.json"
    assert res_file.exists()
    
    data = json.loads(res_file.read_text())
    assert "status" in data
    assert "message" in data
    assert data["message"] == "Mock response"
    assert "data" in data
    
    payload = data.get("data") or {}
    assert "open_questions" in payload
    assert "changed_files" in payload
    assert "usage" in payload


def test_chat_turn_hydrates_continuation_state_before_orchestrator(
    tmp_path, monkeypatch
):
    in_file = tmp_path / "turn_input.json"
    in_file.write_text(
        json.dumps(
            {
                "recent_messages": [{"role": "user", "content": "continue"}],
                "pending_confirmation": "outline_scope",
                "open_questions": ["Which point of view should lead the chapter?"],
            }
        )
    )
    events = []

    class FakeBookState:
        pending_confirmation = "stale_confirmation"

    class FakeBookStateStore:
        state = FakeBookState()

        def __init__(self, *args, **kwargs):
            pass

        def load_or_create(self):
            events.append(("book_load", self.state.pending_confirmation))
            return self.state

        def save(self, state):
            events.append(("book_save", state.pending_confirmation))

    class FakeSessionState:
        open_questions = ["stale question"]

    class FakeSessionStateStore:
        state = FakeSessionState()

        def __init__(self, *args, **kwargs):
            pass

        def load_or_create(self):
            events.append(("session_load", list(self.state.open_questions)))
            return self.state

        def save(self, state):
            events.append(("session_save", list(state.open_questions)))

    class FakeOrchestrator:
        def __init__(self, *args, **kwargs):
            self.initial_state = kwargs.get("initial_state")
            events.append(
                (
                    "orchestrator_init",
                    getattr(self.initial_state, "pending_confirmation", None),
                )
            )

        def handle_user_message(self, text):
            events.append(
                (
                    "handle",
                    self.initial_state.pending_confirmation
                    if self.initial_state is not None
                    else None,
                    list(FakeSessionStateStore.state.open_questions),
                )
            )
            return SimpleNamespace(message="Continued", blocked=False)

    monkeypatch.setattr(wct, "BookStateStore", FakeBookStateStore)
    monkeypatch.setattr(wct, "SessionStateStore", FakeSessionStateStore)
    monkeypatch.setattr(wct, "OpenWriteOrchestrator", FakeOrchestrator)

    assert wct.run_chat_turn(in_file, tmp_path) == 0
    assert events == [
        ("book_load", "stale_confirmation"),
        ("session_load", ["stale question"]),
        ("orchestrator_init", "outline_scope"),
        (
            "handle",
            "outline_scope",
            ["Which point of view should lead the chapter?"],
        ),
    ]
    assert not (
        tmp_path / "data/novels/current/data/workflows/book_state.yaml"
    ).exists()
    assert not (
        tmp_path / "data/novels/current/data/workflows/agent_session.yaml"
    ).exists()

    result = json.loads((tmp_path / "turn_result.json").read_text())
    assert result["data"]["open_questions"] == [
        "Which point of view should lead the chapter?"
    ]


def test_chat_turn_producer_preserves_orchestrator_state(tmp_path, monkeypatch):
    import tools.web_chat_turn as wct

    in_file = tmp_path / "turn_input.json"
    in_file.write_text(json.dumps({"recent_messages": [{"role": "user", "content": "hello"}]}))
    tool_event = {
        "type": "tool_call",
        "tool_name": "read_outline",
        "args": {"path": "outline.md"},
        "result": {"ok": True},
        "message": "Read outline.",
        "sequence": 1,
    }

    class FakeOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def handle_user_message(self, text):
            return SimpleNamespace(
                message="Need the outline scope.",
                blocked=True,
                pending_confirmation="outline_scope",
                open_questions=["Which point of view should lead the chapter?"],
                tool_events=[tool_event],
                usage={"prompt_tokens": 123, "completion_tokens": 45},
            )

    monkeypatch.setattr(wct, "OpenWriteOrchestrator", FakeOrchestrator)

    assert wct.run_chat_turn(in_file, tmp_path) == 0

    result = json.loads((tmp_path / "turn_result.json").read_text())
    assert result["status"] == "blocked"
    assert result["data"]["pending_confirmation"] == "outline_scope"
    assert result["data"]["open_questions"] == [
        "Which point of view should lead the chapter?"
    ]
    assert result["data"]["usage"] == {"prompt_tokens": 123, "completion_tokens": 45}
    assert [
        json.loads(line)
        for line in (tmp_path / "tool_events.jsonl").read_text().splitlines()
    ] == [tool_event]


def test_chat_turn_marks_pending_confirmation_as_blocked(tmp_path, monkeypatch):
    in_file = tmp_path / "turn_input.json"
    in_file.write_text(
        json.dumps({"recent_messages": [{"role": "user", "content": "continue"}]})
    )

    class FakeOrchestrator:
        def __init__(self, *args, **kwargs):
            pass

        def handle_user_message(self, text):
            return SimpleNamespace(
                message="Please confirm the outline scope.",
                blocked=False,
                next_action="confirm_outline_scope",
                pending_confirmation="outline_scope",
                open_questions=[],
            )

    monkeypatch.setattr(wct, "OpenWriteOrchestrator", FakeOrchestrator)

    assert wct.run_chat_turn(in_file, tmp_path) == 0

    result = json.loads((tmp_path / "turn_result.json").read_text())
    assert result["status"] == "blocked"
    assert result["data"]["blocked"] is True
    assert result["data"]["next_action"] == "confirm_outline_scope"
