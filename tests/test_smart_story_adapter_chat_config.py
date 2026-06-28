import pytest
import os
from tools.smart_story_adapter.chat_config import ChatAdapterConfig, ConfigError

def test_chat_adapter_config_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_SESSION_ID", "10")
    monkeypatch.setenv("AGENT_CHAT_TURN_ID", "20")
    monkeypatch.setenv("AGENT_PROJECT_ID", "30")
    monkeypatch.setenv("AGENT_STORY_ID", "40")
    monkeypatch.setenv("AGENT_USER_MESSAGE_ID", "50")
    monkeypatch.setenv("AGENT_SOURCE_BRANCH", "main")
    monkeypatch.setenv("AGENT_SOURCE_COMMIT_SHA", "abcdef123456")
    monkeypatch.setenv("MCP_ENDPOINT", "http://localhost:8000")
    monkeypatch.setenv("MCP_TOKEN", "secret")
    monkeypatch.setenv("GIT_CLONE_URL", "https://github.com/test/repo")
    monkeypatch.setenv("GIT_USERNAME", "gituser")
    monkeypatch.setenv("GIT_PASSWORD", "gitpass")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.setenv("LLM_API_KEY", "sk-123")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENWRITE_LANGUAGE", "en")
    monkeypatch.setenv("WORKSPACE_DIR", "/workspace")

    config = ChatAdapterConfig.from_env()
    assert config.chat_session_id == 10
    assert config.chat_turn_id == 20
    assert config.agent_project_id == 30
    assert config.story_id == 40
    assert config.user_message_id == 50
    assert config.source_branch == "main"
    assert config.source_commit_sha == "abcdef123456"
    assert config.mcp_endpoint == "http://localhost:8000"
    assert config.mcp_token == "secret"
    assert config.git_clone_url == "https://github.com/test/repo"
    assert config.git_username == "gituser"
    assert config.git_password == "gitpass"
    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-4"
    assert config.llm_api_key == "sk-123"
    assert config.llm_base_url == "https://api.openai.com/v1"
    assert config.openwrite_language == "en"
    assert config.workspace == "/workspace"

def test_chat_adapter_config_missing_turn_id(monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_SESSION_ID", "10")
    # missing AGENT_CHAT_TURN_ID
    monkeypatch.setenv("AGENT_PROJECT_ID", "30")
    monkeypatch.setenv("AGENT_STORY_ID", "40")
    monkeypatch.setenv("AGENT_USER_MESSAGE_ID", "50")
    monkeypatch.setenv("AGENT_SOURCE_BRANCH", "main")
    monkeypatch.setenv("MCP_ENDPOINT", "http://localhost:8000")
    monkeypatch.setenv("MCP_TOKEN", "secret")
    monkeypatch.setenv("GIT_CLONE_URL", "https://github.com/test/repo")
    monkeypatch.setenv("GIT_USERNAME", "gituser")
    monkeypatch.setenv("GIT_PASSWORD", "gitpass")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.setenv("LLM_API_KEY", "sk-123")
    monkeypatch.setenv("OPENWRITE_LANGUAGE", "en")
    monkeypatch.setenv("WORKSPACE_DIR", "/workspace")

    with pytest.raises(ConfigError, match="Missing required environment variable: AGENT_CHAT_TURN_ID"):
        ChatAdapterConfig.from_env()

def test_chat_adapter_config_optional_fields(monkeypatch):
    monkeypatch.setenv("AGENT_CHAT_SESSION_ID", "10")
    monkeypatch.setenv("AGENT_CHAT_TURN_ID", "20")
    monkeypatch.setenv("AGENT_PROJECT_ID", "30")
    monkeypatch.setenv("AGENT_STORY_ID", "40")
    monkeypatch.setenv("AGENT_USER_MESSAGE_ID", "50")
    monkeypatch.setenv("AGENT_SOURCE_BRANCH", "main")
    monkeypatch.setenv("MCP_ENDPOINT", "http://localhost:8000")
    monkeypatch.setenv("MCP_TOKEN", "secret")
    monkeypatch.setenv("GIT_CLONE_URL", "https://github.com/test/repo")
    monkeypatch.setenv("GIT_USERNAME", "gituser")
    monkeypatch.setenv("GIT_PASSWORD", "gitpass")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4")
    monkeypatch.setenv("LLM_API_KEY", "sk-123")
    monkeypatch.setenv("OPENWRITE_LANGUAGE", "en")
    monkeypatch.setenv("WORKSPACE_DIR", "/workspace")

    config = ChatAdapterConfig.from_env()
    assert config.source_commit_sha is None
    assert config.llm_base_url is None
