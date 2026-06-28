import json
import yaml
import logging
from pathlib import Path
from tools.smart_story_adapter.chat_io import TurnInput, TurnResult, ToolEvent
from tools.agent.orchestrator import OpenWriteOrchestrator
from tools.agent.book_state import BookStateStore
from tools.agent.session_state import SessionStateStore
from tools.cli import build_cli_tool_executors

logger = logging.getLogger(__name__)

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
                
        if not user_msg.strip():
            turn_result = TurnResult(
                status="failed",
                message="没有找到用户消息。"
            )
            result_path = project_root / "turn_result.json"
            result_path.write_text(json.dumps(turn_result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
            return 1
            
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
        # TODO: Capture and write actual tool events if available
        tool_events_path = project_root / "tool_events.jsonl"
        tool_events_path.write_text("", encoding="utf-8")
        
        status = "blocked" if getattr(result, "blocked", False) else "successful"
        data_payload = {
            "open_questions": [],
            "changed_files": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0}
        }
        
        turn_result = TurnResult(
            status=status,
            message=result.message,
            data=data_payload
        )
        
        result_path = project_root / "turn_result.json"
        result_path.write_text(json.dumps(turn_result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        
        return 0
    except Exception as e:
        logger.error(f"Chat turn 运行失败: {e}", exc_info=True)
        # On error, write error to turn_result.json if possible, then return 1
        result_path = project_root / "turn_result.json"
        try:
            turn_result = TurnResult(
                status="failed",
                message=f"内部错误: {str(e)}"
            )
            result_path.write_text(json.dumps(turn_result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as write_err:
            logger.error(f"Failed to write turn_result.json: {write_err}", exc_info=True)
        return 1
