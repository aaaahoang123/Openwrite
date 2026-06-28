import pytest
from tools.smart_story_adapter.git_paths import is_durable_path

def test_durable_paths():
    assert is_durable_path("novel_config.yaml") is True
    assert is_durable_path("data/novels/123/src/outline.md") is True
    assert is_durable_path("data/novels/123/src/story/chapter1.md") is True
    assert is_durable_path("data/novels/abc/src/characters/hero.md") is True
    assert is_durable_path("data/novels/xyz/src/world/map.md") is True
    assert is_durable_path("data/novels/123/data/manuscript/act1/ch1.md") is True
    assert is_durable_path("data/novels/123/data/style/tone.md") is True
    assert is_durable_path("data/novels/123/data/style/rules.yaml") is True
    assert is_durable_path("data/novels/123/data/world/current_state.md") is True
    assert is_durable_path("data/novels/123/data/workflows/book_state.yaml") is True

def test_non_durable_paths():
    assert is_durable_path("turn_input.json") is False
    assert is_durable_path("tool_events.jsonl") is False
    assert is_durable_path("turn_result.json") is False
    assert is_durable_path("logs/output.log") is False
    assert is_durable_path("data/novels/123/logs/run.log") is False
    assert is_durable_path("traces/provider.json") is False
    assert is_durable_path("some_random_file.txt") is False
