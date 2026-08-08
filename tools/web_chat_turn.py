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
        book_state = state_store.load_or_create(persist=False)
        session_state = session_store.load_or_create(persist=False)

        book_state.pending_confirmation = turn_input.pending_confirmation or ""
        session_state.open_questions = list(turn_input.open_questions)
        
        # 5. Call Orchestrator
        tool_executors = build_cli_tool_executors(project_root)
        orchestrator = OpenWriteOrchestrator(
            project_root=project_root,
            novel_id=novel_id,
            state_store=state_store,
            tool_executors=tool_executors,
            initial_state=book_state,
        )
        
        result = orchestrator.handle_user_message(user_msg)

        # 6. Build and write results
        pending_confirmation = getattr(result, "pending_confirmation", None)
        if pending_confirmation is None:
            pending_confirmation = (
                getattr(getattr(orchestrator, "state", None), "pending_confirmation", "")
                or None
            )

        result_blocked = bool(getattr(result, "blocked", False))
        result_open_questions = getattr(result, "open_questions", None)
        if result_open_questions is not None:
            open_questions = list(result_open_questions)
        elif result_blocked:
            open_questions = list(session_state.open_questions)
        else:
            open_questions = []

        result_tool_events = getattr(result, "tool_events", None) or []
        tool_events_path = project_root / "tool_events.jsonl"
        tool_events_path.write_text(
            "".join(
                json.dumps(event, ensure_ascii=False) + "\n" for event in result_tool_events
            ),
            encoding="utf-8",
        )

        blocked = bool(
            result_blocked
            or pending_confirmation
            or open_questions
        )
        status = "blocked" if blocked else "successful"
        data_payload = {
            "blocked": blocked,
            "next_action": getattr(result, "next_action", None),
            "pending_confirmation": pending_confirmation,
            "open_questions": open_questions,
            "changed_files": [],
            "usage": getattr(result, "usage", None) or {},
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
