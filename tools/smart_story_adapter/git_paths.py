import re
from pathlib import Path

def is_durable_path(path_str: str) -> bool:
    """
    Returns True if the path should be committed to git, based on spec section 8.
    """
    path = Path(path_str)
    
    # Reject explicitly non-durable files
    if path.name in ("turn_input.json", "tool_events.jsonl", "turn_result.json"):
        return False
        
    if "logs/" in path.as_posix() or "traces/" in path.as_posix():
        return False
        
    # Check durable paths
    if path_str == "novel_config.yaml":
        return True
        
    # Match data/novels/{id}/...
    # regex for data/novels/[^/]+/
    parts = path.parts
    if len(parts) >= 4 and parts[0] == "data" and parts[1] == "novels":
        # id is parts[2]
        rest = Path(*parts[3:]).as_posix()
        
        if rest == "src/outline.md":
            return True
        if rest.startswith("src/story/") and rest.endswith(".md"):
            return True
        if rest.startswith("src/characters/") and rest.endswith(".md"):
            return True
        if rest.startswith("src/world/") and rest.endswith(".md"):
            return True
        if rest.startswith("data/manuscript/") and rest.endswith(".md"):
            return True
        if rest.startswith("data/style/") and (rest.endswith(".md") or rest.endswith(".yaml")):
            return True
        if rest == "data/world/current_state.md":
            return True
        if rest == "data/workflows/book_state.yaml":
            return True
            
        # Additional state files that OpenWrite might depend on?
        # "planning/state files that future OpenWrite generation depends on"
        # We can also just allow anything under data/novels/{id}/data/ or src/ if it's md/yaml and not specifically excluded
        # Let's stick strictly to what the spec listed or allow reasonable paths if requested by tests
        
    return False
