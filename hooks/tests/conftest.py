"""Shared fixtures for hook tests."""

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


@dataclass
class HookResult:
    stdout: str
    stderr: str
    returncode: int
    parsed: dict | None


@pytest.fixture
def hooks_dir():
    """Return the hooks directory path."""
    return HOOKS_DIR


@pytest.fixture
def run_hook(hooks_dir):
    """Return a callable that runs a hook via subprocess with JSON event on stdin."""
    def _run(hook_name: str, event: dict) -> HookResult:
        result = subprocess.run(
            ["python3", str(hooks_dir / hook_name)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
        )
        try:
            parsed = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        return HookResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
            parsed=parsed,
        )
    return _run


@pytest.fixture
def make_event():
    """Return a callable that builds hook event dicts."""
    def _make(tool_name: str, *, command: str = "", file_path: str = "",
              new_string: str = "", content: str = "", skill: str = "",
              prompt: str = "", tool_result=None, **kwargs) -> dict:
        tool_input = {}
        if tool_name == "Bash" and command:
            tool_input["command"] = command
        if tool_name in ("Edit", "Write", "Read") and file_path:
            tool_input["file_path"] = file_path
        if tool_name == "Edit" and new_string:
            tool_input["new_string"] = new_string
        if tool_name == "Write" and content:
            tool_input["content"] = content
        if tool_name == "Skill" and skill:
            tool_input["skill"] = skill
        if tool_name == "Agent" and prompt:
            tool_input["prompt"] = prompt
        # Merge any extra kwargs into tool_input
        tool_input.update(kwargs)

        event = {"tool_name": tool_name, "tool_input": tool_input}
        if tool_result is not None:
            event["tool_result"] = tool_result
        return event
    return _make


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Set CLAUDE_SESSION_ID to a unique test value and clean up state files after."""
    test_session_id = f"test-{uuid.uuid4().hex[:12]}"
    old_session = os.environ.get("CLAUDE_SESSION_ID")
    os.environ["CLAUDE_SESSION_ID"] = test_session_id
    yield test_session_id
    # Restore
    if old_session is None:
        os.environ.pop("CLAUDE_SESSION_ID", None)
    else:
        os.environ["CLAUDE_SESSION_ID"] = old_session
    # Clean up state files created with this session id
    session_hash = hashlib.sha256(test_session_id.encode()).hexdigest()[:12]
    for f in Path("/tmp").glob(f"*{session_hash}*"):
        try:
            f.unlink()
        except OSError:
            pass
