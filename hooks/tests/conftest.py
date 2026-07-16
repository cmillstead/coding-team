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
    parser.addoption(
        "--run-llm-eval",
        action="store_true",
        default=False,
        help="Run llm_eval skill-routing tests that shell out to the real claude CLI",
    )


def pytest_configure(config):
    """Register custom markers and root pytest's tmp dirs outside /tmp.

    Root cause (task #12): write-guard.py's is_orchestrator_file() treats
    ANY path starting with the literal prefix "/tmp" as an always-allowed
    orchestrator scratch file (by design, for real /tmp scratch work). On
    Linux (incl. GitHub Actions ubuntu-latest), /tmp is a real, non-symlinked
    directory, so pytest's default tmp_path base resolves to a literal
    /tmp/pytest-of-<user>/... path — a Phase5 test repo built under tmp_path
    then silently satisfies is_orchestrator_file() and the guard under test
    never fires, regardless of active-plan detection. On macOS this never
    reproduces because /tmp is a symlink to /private/tmp and pytest resolves
    tmp_path through it, so local runs looked green while CI was red.
    Rooting tmp dirs at the repo root (NOT under hooks/ — write-guard.py's
    is_instruction_file() treats any .py under a path containing a "hooks"
    segment as behavioral, which a hooks/.pytest-tmp/ placement would have
    made every test .py file falsely match) means no test path can start
    with "/tmp" or contain "hooks" on any platform. Only applies when
    --basetemp wasn't explicitly passed on the command line.
    """
    config.addinivalue_line(
        "markers",
        "llm_judge: marks tests that require real LLM calls (deselect with '-m \"not llm_judge\"')",
    )
    config.addinivalue_line(
        "markers",
        "smoke: Tier 1 agent smoke tests (structural validation, no LLM calls)",
    )
    if config.option.basetemp is None:
        base = HOOKS_DIR.parent / ".pytest-tmp"
        base.mkdir(exist_ok=True)
        config.option.basetemp = str(base)


# ---------------------------------------------------------------------------
# Default-skip gate for expensive markers (llm_eval, llm_judge)
# ---------------------------------------------------------------------------

# Marker name -> the opt-in CLI flag (as registered in pytest_addoption above)
# that unlocks it. Both markers are documented as "skipped by default" (see
# pytest.ini for llm_eval, conftest's --run-llm-judge help text) but neither
# marker had an actual collection-time skip mechanism wired up, so a bare
# `pytest` collected AND RAN them, spawning the real `claude` CLI.
_GATED_MARKERS = {
    "llm_eval": "run_llm_eval",
    "llm_judge": "run_llm_judge",
}


def pytest_collection_modifyitems(config, items):
    """Skip llm_eval/llm_judge tests by default unless explicitly opted in.

    A test is left ungated (allowed to run) if the caller passed the marker's
    matching `--run-<marker>` flag, or explicitly requested the marker via
    `-m <marker>` (e.g. `pytest -m llm_eval`), which is an unambiguous signal
    the caller wants those tests to execute.
    """
    markexpr = config.option.markexpr or ""
    for marker_name, flag_dest in _GATED_MARKERS.items():
        opted_in = config.getoption(flag_dest, default=False) or marker_name in markexpr
        if opted_in:
            continue
        skip_marker = pytest.mark.skip(
            reason=(
                f"{marker_name}: needs real claude CLI; pass --run-{marker_name.replace('_', '-')} "
                f"or -m {marker_name} to run"
            )
        )
        for item in items:
            if item.get_closest_marker(marker_name) is not None:
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# C5 hermeticity — session-start env scrub
# ---------------------------------------------------------------------------

# Flags that, when set in the ambient process env, leak into every subprocess
# spawned via _run()'s {**os.environ, **env} merge and silently bypass write-guard
# / git-safety-guard "should block" tests. Popped at session start so the scrubbed
# os.environ is the BASE every test inherits. Tests that explicitly pass
# env={"FLAG": "1"} still WIN because the _run() merge layers their explicit
# values OVER the scrubbed base. GIT_SAFETY_ALLOW_COMPOUND ships enabled ("1") in
# settings.json, so without scrubbing it a local run would inherit it and the
# compound-block tests (which assert the deny path fires) would silently fall
# through instead — the override disables the block unconditionally, not just
# for non-git compounds.
_WRITE_GUARD_AMBIENT_FLAGS = (
    "WRITE_GUARD_ALLOW_INSTRUCTION_EDIT",
    "WRITE_GUARD_ALLOW_MIGRATION_EDIT",
    "GIT_SAFETY_ALLOW_COMPOUND",
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
