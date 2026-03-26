"""Tests for hooks/_lib/ utilities using subprocess invocation."""

import hashlib
import json
import subprocess
import uuid
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def run_python(code: str, stdin_data: str = "") -> subprocess.CompletedProcess:
    """Run a Python snippet with the hooks dir on sys.path."""
    full_code = f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n{code}"
    return subprocess.run(
        ["python3", "-c", full_code],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )


# ---------------------------------------------------------------------------
# parse_event
# ---------------------------------------------------------------------------

class TestParseEvent:
    def test_valid_json(self):
        event = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        result = run_python(
            "from _lib.event import parse_event; import json; print(json.dumps(parse_event()))",
            stdin_data=json.dumps(event),
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["tool_name"] == "Bash"

    def test_invalid_json(self):
        result = run_python(
            "from _lib.event import parse_event; import json; print(json.dumps(parse_event()))",
            stdin_data="not json at all",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed == {}

    def test_empty_string(self):
        result = run_python(
            "from _lib.event import parse_event; import json; print(json.dumps(parse_event()))",
            stdin_data="",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed == {}


# ---------------------------------------------------------------------------
# get_state_file
# ---------------------------------------------------------------------------

class TestGetStateFile:
    def test_returns_session_specific_path(self):
        session_id = f"test-{uuid.uuid4().hex[:8]}"
        result = run_python(
            f"import os; os.environ['CLAUDE_SESSION_ID'] = {session_id!r}\n"
            "from _lib.state import get_state_file; print(get_state_file('prefix'))",
        )
        assert result.returncode == 0
        path = result.stdout.strip()
        session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
        assert f"prefix-{session_hash}" in path
        assert path.startswith("/tmp/")


# ---------------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------------

class TestLoadSaveState:
    def test_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        result = run_python(
            f"from _lib.state import load_state; from pathlib import Path; "
            f"print(load_state(Path({str(missing)!r})))",
        )
        assert result.returncode == 0
        assert "{}" in result.stdout

    def test_valid_file(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"key": "value"}))
        result = run_python(
            f"from _lib.state import load_state; from pathlib import Path; import json; "
            f"print(json.dumps(load_state(Path({str(state_file)!r}))))",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["key"] == "value"

    def test_corrupt_file(self, tmp_path):
        state_file = tmp_path / "corrupt.json"
        state_file.write_text("not valid json {{{")
        result = run_python(
            f"from _lib.state import load_state; from pathlib import Path; "
            f"print(load_state(Path({str(state_file)!r})))",
        )
        assert result.returncode == 0
        assert "{}" in result.stdout

    def test_save_then_load(self, tmp_path):
        state_file = tmp_path / "roundtrip.json"
        data = {"counter": 42, "items": ["a", "b"]}
        result = run_python(
            f"from _lib.state import save_state, load_state; from pathlib import Path; import json; "
            f"p = Path({str(state_file)!r}); "
            f"save_state(p, {json.dumps(data)}); "
            f"print(json.dumps(load_state(p)))",
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["counter"] == 42
        assert parsed["items"] == ["a", "b"]


# ---------------------------------------------------------------------------
# extract_git_command
# ---------------------------------------------------------------------------

class TestExtractGitCommand:
    def test_git_commit(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("git commit -m \\"foo\\""))',
        )
        assert result.stdout.strip() == "commit"

    def test_not_git_command(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("ls -la"))',
        )
        assert result.stdout.strip() == "None"

    def test_git_push(self):
        result = run_python(
            'from _lib.git import extract_git_command; '
            'print(extract_git_command("git push origin main"))',
        )
        assert result.stdout.strip() == "push"


# ---------------------------------------------------------------------------
# is_broad_add
# ---------------------------------------------------------------------------

class TestIsBroadAdd:
    @pytest.mark.parametrize("cmd", [
        "git add -A",
        "git add --all",
        "git add .",
    ])
    def test_broad_add_detected(self, cmd):
        result = run_python(
            f'from _lib.git import is_broad_add; print(is_broad_add({cmd!r}))',
        )
        assert result.stdout.strip() == "True"

    def test_specific_file_not_broad(self):
        result = run_python(
            'from _lib.git import is_broad_add; '
            'print(is_broad_add("git add src/main.py"))',
        )
        assert result.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# block / allow / allow_with_reason
# ---------------------------------------------------------------------------

class TestOutputFunctions:
    def test_block_structure(self):
        result = run_python(
            'from _lib.output import block; block("test reason")',
        )
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "block"
        assert parsed["reason"] == "test reason"

    def test_allow_structure(self):
        result = run_python(
            'from _lib.output import allow; allow()',
        )
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "allow"
        assert "reason" not in parsed

    def test_allow_with_reason_structure(self):
        result = run_python(
            'from _lib.output import allow_with_reason; '
            'allow_with_reason("advisory msg")',
        )
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "allow"
        assert parsed["reason"] == "advisory msg"
