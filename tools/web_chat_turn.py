import json
import yaml
from pathlib import Path
from tools.smart_story_adapter.chat_io import TurnInput, TurnResult, ToolEvent
from tools.agent.orchestrator import OpenWriteOrchestrator
from tools.agent.book_state import BookStateStore
from tools.agent.session_state import SessionStateStore
from tools.cli import build_cli_tool_executors

def run_chat_turn(input_path: Path, project_root: Path) -> int:
    try:
        # 1. Parse TurnInput
        input_data = json.loads(input_path.read_text(encoding="utf-8"))
        turn_input = TurnInput.from_json(input_data)
        
        # 2. Extract latest user message
        user_msg = ""
        for msg in reversed(turn_input.recent_messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break
                
        # 3. Get novel_id
        config_path = project_root / "novel_config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}
        novel_id = config.get("novel_id", "current")
        
        # 4. Instantiate stores
        state_store = BookStateStore(project_root, novel_id)
        session_store = SessionStateStore(project_root, novel_id)
        
        # Hydrate state
        state_store.load_or_create()
        session_store.load_or_create()
        
        # 5. Call Orchestrator
        tool_executors = build_cli_tool_executors(project_root)
        orchestrator = OpenWriteOrchestrator(
            project_root=project_root,
            novel_id=novel_id,
            state_store=state_store,
            tool_executors=tool_executors
        )
        
        result = orchestrator.handle_user_message(user_msg)
        
        # 6. Build and write results
        # Write tool_events.jsonl (empty for now, can be populated if we capture them)
        tool_events_path = project_root / "tool_events.jsonl"
        tool_events_path.write_text("", encoding="utf-8")
        
        turn_result = {
            "assistant_message": result.message,
            "blocked": getattr(result, "blocked", False),
            "open_questions": [],
            "changed_files": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
        }
        
        result_path = project_root / "turn_result.json"
        result_path.write_text(json.dumps(turn_result, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return 0
    except Exception as e:
        # On error, write error to turn_result.json if possible, then return 1
        result_path = project_root / "turn_result.json"
        try:
            turn_result = {
                "assistant_message": f"内部错误: {str(e)}",
                "blocked": True,
                "open_questions": [],
                "changed_files": [],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0}
            }
            result_path.write_text(json.dumps(turn_result, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass
        return 1
