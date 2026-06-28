import pytest
from tools.smart_story_adapter.chat_io import TurnInput, ToolEvent, TurnResult

def test_turn_input_roundtrip():
    data = {
        "recent_messages": [{"role": "user", "content": "hello"}],
        "pending_confirmation": {"type": "action", "description": "do something"},
        "open_questions": [{"id": 1, "question": "why?"}],
        "source_sha": "abcdef123"
    }
    obj = TurnInput.from_json(data)
    assert obj.recent_messages == data["recent_messages"]
    assert obj.pending_confirmation == data["pending_confirmation"]
    assert obj.open_questions == data["open_questions"]
    assert obj.source_sha == data["source_sha"]
    assert obj.to_json() == data

def test_tool_event_roundtrip():
    data = {
        "event_type": "mcp_call",
        "payload": {"method": "read", "uri": "file.txt"},
        "timestamp": 123456.789
    }
    obj = ToolEvent.from_json(data)
    assert obj.event_type == data["event_type"]
    assert obj.payload == data["payload"]
    assert obj.timestamp == data["timestamp"]
    assert obj.to_json() == data

def test_turn_result_roundtrip():
    data = {
        "status": "blocked",
        "message": "waiting for user input",
        "data": {"missing_info": "email"}
    }
    obj = TurnResult.from_json(data)
    assert obj.status == "blocked"
    assert obj.message == "waiting for user input"
    assert obj.data == {"missing_info": "email"}
    assert obj.to_json() == data
