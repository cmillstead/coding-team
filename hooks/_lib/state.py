"""Session state management utilities for Claude Code hooks."""

import hashlib
import json
import os
import time
from pathlib import Path


def get_session_id() -> str:
    """Get the current session ID from environment."""
    return os.environ.get("CLAUDE_SESSION_ID",
                          os.environ.get("SESSION_ID", "default"))


def get_state_file(prefix: str) -> Path:
    """Return a session-scoped state file path."""
    session_hash = hashlib.sha256(get_session_id().encode()).hexdigest()[:12]
    return Path(f"/tmp/{prefix}-{session_hash}.json")


def load_state(path: Path, default: dict | None = None) -> dict:
    """Load JSON state from a file, returning default on any error."""
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default or {}


def save_state(path: Path, state: dict) -> None:
    """Write JSON state to a file, ignoring write errors."""
    try:
        path.write_text(json.dumps(state))
    except OSError:
        pass


def is_stale(state: dict, max_age: int = 7200) -> bool:
    """Check if state's last_updated timestamp is older than max_age seconds."""
    last_updated = state.get("last_updated")
    if last_updated is None:
        return True
    return (time.time() - last_updated) > max_age
