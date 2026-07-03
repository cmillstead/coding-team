"""Shared fixtures for hook tests."""

import hashlib
import json
import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest


HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/


def pytest_addoption(parser):
    """Register custom CLI options for hook tests."""
    parser.addoption(
        "--run-llm-judge",
        action="store_true",
        default=False,
        help="Run expensive LLM-as-judge agent quality tests (~$0.05 each)",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "llm_judge: marks tests that require real LLM calls (deselect with '-m \"not llm_judge\"')",
    )
    config.addinivalue_line(
        "markers",
        "smoke: Tier 1 agent smoke tests (structural validation, no LLM calls)",
    )


# ---------------------------------------------------------------------------
# C5 hermeticity — session-start env scrub
# ---------------------------------------------------------------------------

# Flags that, when set in the ambient process env, leak into every subprocess
# spawned via _run()'s {**os.environ, **env} merge and silently bypass write-guard
# "should block" tests. Popped at session start so the scrubbed os.environ is the
# BASE every test inherits. Tests that explicitly pass env={"FLAG": "1"} still WIN
# because the _run() merge layers their explicit values OVER the scrubbed base.
_WRITE_GUARD_AMBIENT_FLAGS = (
    "WRITE_GUARD_ALLOW_INSTRUCTION_EDIT",
    "WRITE_GUARD_ALLOW_MIGRATION_EDIT",
)


@pytest.fixture(scope="session", autouse=True)
def scrub_write_guard_ambient_flags():
    """Pop write-guard override flags from os.environ for the duration of the session.

    Removes WRITE_GUARD_ALLOW_INSTRUCTION_EDIT and WRITE_GUARD_ALLOW_MIGRATION_EDIT
    from the process environment at session start and restores them at teardown.
    This ensures that any ambient flag (e.g. set in settings.json or the user's
    shell) does not leak into "should block" subprocess tests.

    Tests that explicitly pass env={"WRITE_GUARD_ALLOW_*": "1"} to _run() are
    unaffected — the {**os.environ, **env} merge in _run() layers their explicit
    values over the scrubbed base, so explicit overrides still take precedence.
    """
    saved = {flag: os.environ.pop(flag, None) for flag in _WRITE_GUARD_AMBIENT_FLAGS}
    yield
    for flag, value in saved.items():
        if value is not None:
            os.environ[flag] = value
        else:
            os.environ.pop(flag, None)


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
    """Set session env vars to a unique test value and clean up state files after.

    Overrides both CLAUDE_CODE_SESSION_ID (preferred) and CLAUDE_SESSION_ID (legacy)
    so that get_session_id() uses the test-controlled value in subprocess hooks.
    """
    test_session_id = f"test-{uuid.uuid4().hex[:12]}"
    old_cc_session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    old_session = os.environ.get("CLAUDE_SESSION_ID")
    # Set both so the highest-priority var controls the test session
    os.environ["CLAUDE_CODE_SESSION_ID"] = test_session_id
    os.environ["CLAUDE_SESSION_ID"] = test_session_id
    yield test_session_id
    # Restore CLAUDE_CODE_SESSION_ID
    if old_cc_session is None:
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
    else:
        os.environ["CLAUDE_CODE_SESSION_ID"] = old_cc_session
    # Restore CLAUDE_SESSION_ID
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
