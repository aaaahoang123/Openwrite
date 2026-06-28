import os
from dataclasses import dataclass
from typing import Optional

class ConfigError(Exception):
    pass

@dataclass(frozen=True)
class ChatAdapterConfig:
    chat_session_id: int
    chat_turn_id: int
    agent_project_id: int
    story_id: int
    user_message_id: int
    source_branch: str
    source_commit_sha: str | None
    mcp_endpoint: str
    mcp_token: str
    git_clone_url: str
    git_username: str
    git_password: str
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str | None
    openwrite_language: str
    workspace: str

    @classmethod
    def from_env(cls) -> "ChatAdapterConfig":
        def get_required(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise ConfigError(f"Missing required environment variable: {key}")
            return val

        def get_required_int(key: str) -> int:
            val = get_required(key)
            try:
                return int(val)
            except ValueError:
                raise ConfigError(f"Environment variable {key} must be an integer, got {val}")

        return cls(
            chat_session_id=get_required_int("AGENT_CHAT_SESSION_ID"),
            chat_turn_id=get_required_int("AGENT_CHAT_TURN_ID"),
            agent_project_id=get_required_int("AGENT_PROJECT_ID"),
            story_id=get_required_int("AGENT_STORY_ID"),
            user_message_id=get_required_int("AGENT_USER_MESSAGE_ID"),
            source_branch=get_required("AGENT_SOURCE_BRANCH"),
            source_commit_sha=os.environ.get("AGENT_SOURCE_COMMIT_SHA") or None,
            mcp_endpoint=get_required("MCP_ENDPOINT"),
            mcp_token=get_required("MCP_TOKEN"),
            git_clone_url=get_required("GIT_CLONE_URL"),
            git_username=get_required("GIT_USERNAME"),
            git_password=get_required("GIT_PASSWORD"),
            llm_provider=get_required("LLM_PROVIDER"),
            llm_model=get_required("LLM_MODEL"),
            llm_api_key=get_required("LLM_API_KEY"),
            llm_base_url=os.environ.get("LLM_BASE_URL") or None,
            openwrite_language=get_required("OPENWRITE_LANGUAGE"),
            workspace=get_required("WORKSPACE_DIR"),
        )
