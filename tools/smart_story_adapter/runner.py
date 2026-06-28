from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

import yaml

from .config import AdapterConfig, AdapterError
from .git_ops import GitOps
from .mcp import McpClient
from .outputs import collect_private_drafts
from .chat_config import ChatAdapterConfig
from .chat_io import TurnInput, TurnResult
from .git_paths import is_durable_path
import json
import time


class ProgressClient(Protocol):
    def report_progress(self, payload: dict) -> dict: ...
    def import_private_draft(self, payload: dict) -> dict: ...

class ChatProgressClient(Protocol):
    def report_chat_turn_progress(self, payload: dict) -> dict: ...
    def import_private_draft(self, payload: dict) -> dict: ...
    def complete_chat_turn(self, payload: dict) -> dict: ...


RunOpenWrite = Callable[[Path, AdapterConfig], int]
RunChatOpenWrite = Callable[[Path, ChatAdapterConfig], int]

class SmartStoryAdapterRunner:
    def __init__(
        self,
        config: AdapterConfig,
        mcp: ProgressClient | None = None,
        git_ops: GitOps | None = None,
        run_openwrite: RunOpenWrite | None = None,
    ) -> None:
        self.config = config
        self.workspace = Path(config.workspace)
        self.mcp = mcp or McpClient(config.mcp_endpoint, config.mcp_token)
        self.git_ops = git_ops or GitOps()
        self.run_openwrite = run_openwrite or default_run_openwrite

    def run(self) -> int:
        try:
            self._progress("preparing", 1, "Adapter started.")
            self.git_ops.clone_or_fetch(
                self.workspace,
                self.config.git_clone_url,
                self.config.git_username,
                self.config.git_password,
                self.config.source_branch,
            )
            self.git_ops.verify_commit(self.workspace, self.config.source_commit_sha)
            novel_id = self._novel_id()
            self._progress("running", 20, "Running OpenWrite.")
            code = self.run_openwrite(self.workspace, self.config)
            if code != 0:
                raise AdapterError("OpenWrite command failed", "runtime_crashed", "OpenWrite không tạo được bản nháp.")
            final_commit = self.git_ops.commit_all(self.workspace, self._commit_message())
            self.git_ops.push(self.workspace, self.config.source_branch)
            self._progress("submitting", 80, "Submitting private drafts.", commit_sha=final_commit)
            output_ids = []
            for draft in collect_private_drafts(self.workspace, novel_id, final_commit, self.config.source_branch):
                draft["agent_project_id"] = self.config.agent_project_id
                result = self.mcp.import_private_draft(draft)
                output_ids.append({"type": "private_draft", "id": result.get("private_draft_id"), "duplicate": result.get("duplicate", False)})
            self._progress("succeeded", 100, "Completed.", commit_sha=final_commit, output_ids=output_ids)
            return 0
        except AdapterError as exc:
            import sys
            print(f"AdapterError: {exc}", file=sys.stderr)
            try:
                self._progress("failed", 100, exc.user_message, failure_category=exc.failure_category, user_message=exc.user_message)
            except Exception as report_exc:
                print(f"Failed to report error to backend: {report_exc}", file=sys.stderr)
            return 1

    def _novel_id(self) -> str:
        config_path = self.workspace / "novel_config.yaml"
        try:
            text = config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise AdapterError(f"Failed to read novel_config: {exc}", "configuration_missing", "Workspace thiếu novel_config.yaml hợp lệ.") from exc
        novel_id = str(data.get("novel_id", "")).strip()
        if not novel_id:
            raise AdapterError("novel_config.yaml missing novel_id", "configuration_missing", "Workspace thiếu novel_id.")
        return novel_id

    def _progress(self, status: str, percent: int, message: str, **extra: object) -> None:
        payload = {
            "agent_project_id": self.config.agent_project_id,
            "status": status,
            "progress_percent": percent,
            "message": message,
            "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        }
        payload.update({key: value for key, value in extra.items() if value is not None})
        self.mcp.report_progress(payload)

    def _commit_message(self) -> str:
        return (
            f"Smart Story hosted run {self.config.agent_run_id}\n\n"
            f"Agent project: {self.config.agent_project_id}\n"
            f"Story: {self.config.story_id}\n"
            f"Task: {self.config.task_type}\n"
            f"Source commit: {self.config.source_commit_sha or 'unknown'}"
        )


def default_run_openwrite(workspace: Path, config: AdapterConfig) -> int:
    env = os.environ.copy()
    env.update(config.openwrite_env())
    try:
        process = subprocess.run(
            ["openwrite", "multi-write", "next", "--no-review"],
            cwd=workspace,
            env=env,
            check=False,
        )
        return process.returncode
    except OSError as exc:
        raise AdapterError(f"Failed to execute openwrite: {exc}", "runtime_crashed", "Không thể thực thi openwrite.") from exc

def default_run_chat_openwrite(workspace: Path, config: ChatAdapterConfig) -> int:
    env = os.environ.copy()
    env.update(config.openwrite_env())
    try:
        process = subprocess.run(
            ["openwrite", "chat-turn", "--in", "turn_input.json"],
            cwd=workspace,
            env=env,
            check=False,
        )
        return process.returncode
    except OSError as exc:
        raise AdapterError(f"Failed to execute openwrite chat-turn: {exc}", "runtime_crashed", "Không thể thực thi openwrite.") from exc

class ChatTurnAdapterRunner:
    def __init__(
        self,
        config: ChatAdapterConfig,
        mcp: ChatProgressClient | None = None,
        git_ops: GitOps | None = None,
        run_openwrite: RunChatOpenWrite | None = None,
    ) -> None:
        self.config = config
        self.workspace = Path(config.workspace)
        self.mcp = mcp or McpClient(config.mcp_endpoint, config.mcp_token)
        self.git_ops = git_ops or GitOps()
        self.run_openwrite = run_openwrite or default_run_chat_openwrite

    def run(self) -> int:
        try:
            self._progress("started")
            self.git_ops.clone_or_fetch(
                self.workspace,
                self.config.git_clone_url,
                self.config.git_username,
                self.config.git_password,
                self.config.source_branch,
            )
            self.git_ops.verify_commit(self.workspace, self.config.source_commit_sha)
            novel_id = self._novel_id()
            
            # Fetch and write turn_input.json
            input_path = self.workspace / "turn_input.json"
            input_payload = os.environ.get("AGENT_TURN_PAYLOAD", "{}")
            input_path.write_text(input_payload, encoding="utf-8")

            self._progress("running")
            code = self.run_openwrite(self.workspace, self.config)
            
            if code != 0:
                # We still try to read results, maybe it failed gracefully
                pass

            # Read results
            result_path = self.workspace / "turn_result.json"
            if not result_path.exists():
                raise AdapterError("OpenWrite crashed without result", "runtime_crashed", "OpenWrite không tạo được kết quả.")
            
            result_data = json.loads(result_path.read_text(encoding="utf-8"))
            turn_result = TurnResult.from_json(result_data)

            events_path = self.workspace / "tool_events.jsonl"
            tool_events = []
            if events_path.exists():
                for line in events_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        tool_events.append(json.loads(line))
            
            # Commit durable files
            changed_files = self.git_ops.get_changed_files(self.workspace)
            durable_files = [f for f in changed_files if is_durable_path(f)]
            
            final_commit = None
            if durable_files:
                final_commit = self.git_ops.commit_files(self.workspace, durable_files, self._commit_message())
                self.git_ops.push(self.workspace, self.config.source_branch)
            elif self.config.source_commit_sha:
                final_commit = self.config.source_commit_sha

            self._progress("submitting")

            # Import drafts
            output_ids = []
            if final_commit:
                for draft in collect_private_drafts(self.workspace, novel_id, final_commit, self.config.source_branch):
                    draft["agent_project_id"] = self.config.agent_project_id
                    result = self.mcp.import_private_draft(draft)
                    output_ids.append({"type": "private_draft", "id": result.get("private_draft_id"), "duplicate": result.get("duplicate", False)})

            # Call complete_chat_turn with retry
            payload = {
                "chat_session_id": self.config.chat_session_id,
                "chat_turn_id": self.config.chat_turn_id,
                "status": turn_result.status,
                "message": turn_result.message,
                "data": turn_result.data,
                "tool_events": tool_events,
                "commit_sha": final_commit,
                "output_ids": output_ids
            }
            self._complete_with_retry(payload)

            return 0
        except AdapterError as exc:
            import sys
            print(f"AdapterError: {exc}", file=sys.stderr)
            try:
                self._complete_failed(exc)
            except Exception as report_exc:
                print(f"Failed to report error to backend: {report_exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            import sys
            print(f"Unexpected error: {exc}", file=sys.stderr)
            try:
                self._complete_failed(AdapterError(str(exc), "runtime_crashed", "Lỗi không xác định."))
            except Exception as report_exc:
                print(f"Failed to report error to backend: {report_exc}", file=sys.stderr)
            return 1

    def _complete_with_retry(self, payload: dict) -> None:
        import time
        for attempt in range(3):
            try:
                self.mcp.complete_chat_turn(payload)
                return
            except Exception as e:
                import sys
                print(f"MCP complete_chat_turn attempt {attempt+1} failed: {e}", file=sys.stderr)
                time.sleep(2 ** attempt)
        # Final attempt
        self.mcp.complete_chat_turn(payload)


    def _novel_id(self) -> str:
        config_path = self.workspace / "novel_config.yaml"
        try:
            text = config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise AdapterError(f"Failed to read novel_config: {exc}", "configuration_missing", "Workspace thiếu novel_config.yaml hợp lệ.") from exc
        novel_id = str(data.get("novel_id", "")).strip()
        if not novel_id:
            raise AdapterError("novel_config.yaml missing novel_id", "configuration_missing", "Workspace thiếu novel_id.")
        return novel_id

    def _progress(self, status: str, result_data: dict | None = None) -> None:
        payload = {
            "chat_session_id": self.config.chat_session_id,
            "chat_turn_id": self.config.chat_turn_id,
            "status": status,
        }
        if result_data:
            payload["result_data"] = result_data
        self.mcp.report_chat_turn_progress(payload)

    def _commit_message(self) -> str:
        return (
            f"Smart Story chat session {self.config.chat_session_id} turn {self.config.chat_turn_id}\n\n"
            f"Agent project: {self.config.agent_project_id}\n"
            f"Story: {self.config.story_id}\n"
            f"Source commit: {self.config.source_commit_sha or 'unknown'}"
        )

    def _complete_failed(self, exc: AdapterError) -> None:
        payload = {
            "chat_session_id": self.config.chat_session_id,
            "chat_turn_id": self.config.chat_turn_id,
            "status": "failed",
            "message": exc.user_message,
            "data": {
                "failure_category": exc.failure_category,
                "internal_error": str(exc)
            },
            "tool_events": [],
            "commit_sha": None,
            "output_ids": []
        }
        self._complete_with_retry(payload)

