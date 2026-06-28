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
            "assistant_message": "Hello",
            "blocked": False,
            "open_questions": [],
            "changed_files": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
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
    assert "assistant_message" in data
    assert "blocked" in data
    assert "open_questions" in data
    assert "changed_files" in data
    assert "usage" in data

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
    assert "assistant_message" in data
    assert data["assistant_message"] == "Mock response"
    assert "blocked" in data
    assert "open_questions" in data
    assert "changed_files" in data
    assert "usage" in data

