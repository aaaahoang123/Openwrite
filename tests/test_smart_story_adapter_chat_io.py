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

def test_tool_event_ordering():
    events_data = [
        {"event_type": "mcp_call", "payload": {"method": "read", "uri": "file.txt"}, "timestamp": 1.0},
        {"event_type": "mcp_response", "payload": {"result": "ok"}, "timestamp": 2.0},
        {"event_type": "mcp_call", "payload": {"method": "write", "uri": "file2.txt"}, "timestamp": 3.0},
    ]
    
    # Simulate writing to jsonl
    jsonl_lines = [ToolEvent.from_json(d).to_json() for d in events_data]
    
    # Assert order is preserved
    assert jsonl_lines == events_data
    assert jsonl_lines[0]["timestamp"] < jsonl_lines[1]["timestamp"]
    assert jsonl_lines[1]["timestamp"] < jsonl_lines[2]["timestamp"]

def test_turn_result_statuses():
    # Successful
    success_data = {
        "status": "successful",
        "message": "done",
        "data": {"output": "ok"}
    }
    success_obj = TurnResult.from_json(success_data)
    assert success_obj.status == "successful"
    assert success_obj.to_json() == success_data

    # Blocked
    blocked_data = {
        "status": "blocked",
        "message": "waiting for user input",
        "data": {"missing_info": "email"}
    }
    blocked_obj = TurnResult.from_json(blocked_data)
    assert blocked_obj.status == "blocked"
    assert blocked_obj.to_json() == blocked_data

    # Failed
    failed_data = {
        "status": "failed",
        "message": "internal error",
        "data": {"traceback": "..."}
    }
    failed_obj = TurnResult.from_json(failed_data)
    assert failed_obj.status == "failed"
    assert failed_obj.to_json() == failed_data
