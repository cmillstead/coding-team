"""Tests for pretooluse-dispatcher.py.

Acceptance tests that verify the consolidation invariants:
  1. write-guard BLOCK: dispatcher output identical to write-guard.py alone.
  2. write-guard ALLOW: benign Write event passes through.
  3. git-safety-guard BLOCK: dispatcher output identical to git-safety-guard.py alone.
  4. git-safety-guard ALLOW: benign Bash not blocked.
  5. codesight prompt injection: Agent event gets CODESIGHT_INSTRUCTION injected.
  6. Disable escape hatch: CT_PRETOOLUSE_DISPATCHER_DISABLE=1 → exit 0 no output.
  7. Skip escape hatch: CT_PRETOOLUSE_DISPATCHER_SKIP excludes named handler.
  8. Unknown tool name: exits 0 silently.

# mock-ok: base64-encoded test input for dispatcher acceptance tests, not real mock usage
"""

import base64
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
PRETOOLUSE_DISPATCHER = HOOKS_DIR / "pretooluse-dispatcher.py"
WRITE_GUARD = HOOKS_DIR / "write-guard.py"
GIT_SAFETY_GUARD = HOOKS_DIR / "git-safety-guard.py"

# Load dispatcher module for unit tests (filename has a hyphen → importlib required)
_spec = importlib.util.spec_from_file_location("ptd", PRETOOLUSE_DISPATCHER)
_ptd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ptd)


def _run_script(
    script: Path,
    event: dict,
    env: dict | None = None,
) -> tuple[str, int]:
    """Run hook script via subprocess with event on stdin. Return (stdout, returncode)."""
    merged_env = {**os.environ, **(env or {})}
    # Ensure write-guard override flags are absent to get clean guard behaviour.
    merged_env.pop("WRITE_GUARD_ALLOW_INSTRUCTION_EDIT", None)
    merged_env.pop("WRITE_GUARD_ALLOW_MIGRATION_EDIT", None)
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=20,
        env=merged_env,
    )
    return result.stdout, result.returncode


# Base64-encoded test content with mock usage to trigger write-guard.
# mock-ok: base64-encoded test input for dispatcher acceptance test, not real mock usage
_MOCK_CONTENT = base64.b64decode(
    "ZnJvbSB1bml0dGVzdC5tb2NrIGltcG9ydCBNYWdpY01vY2sKCmRlZiB0ZXN0X2ZvbygpOgogICAgbSA9IE1hZ2ljTW9jaygpCg=="
).decode()


# ---------------------------------------------------------------------------
# Unit tests for internal helpers (no env manipulation needed)
# ---------------------------------------------------------------------------

class TestIsSkipped:
    def test_matching_basename_returns_true(self):
        assert _ptd._is_skipped("/some/path/write-guard.py", {"write-guard.py"})

    def test_non_matching_returns_false(self):
        assert not _ptd._is_skipped("/some/path/write-guard.py", {"other.py"})

    def test_empty_skip_set_returns_false(self):
        assert not _ptd._is_skipped("/some/path/write-guard.py", set())

    def test_rtk_basename_check(self):
        assert _ptd._is_skipped("rtk", {"rtk"})


class TestRunHandler:
    """Unit tests for _run_handler: isolation contract."""

    def test_silent_script_returns_empty_stdout(self, tmp_path):
        script = tmp_path / "silent.py"
        script.write_text("import sys\nsys.exit(0)\n")
        stdout, rc = _ptd._run_handler([sys.executable, str(script)], "{}")
        assert stdout == ""
        assert rc == 0

    def test_output_script_returns_output(self, tmp_path):
        script = tmp_path / "output.py"
        script.write_text(
            'import json\nprint(json.dumps({"decision":"block","reason":"test"}))\n'
        )
        stdout, rc = _ptd._run_handler([sys.executable, str(script)], "{}")
        assert '"decision"' in stdout

    def test_crashing_script_returns_empty_stdout(self, tmp_path):
        crash = tmp_path / "crash.py"
        crash.write_text("raise RuntimeError('boom')\n")
        stdout, rc = _ptd._run_handler([sys.executable, str(crash)], "{}")
        assert stdout == ""
        # rc reflects the subprocess exit code (non-zero on crash);
        # isolation is at routing level: empty stdout means dispatcher skips.

    def test_timeout_returns_empty(self, tmp_path):
        slow = tmp_path / "slow.py"
        slow.write_text("import time\ntime.sleep(10)\n")
        stdout, rc = _ptd._run_handler(
            [sys.executable, str(slow)], "{}", timeout=1
        )
        assert stdout == ""
        assert rc == 0

    def test_missing_interpreter_returns_empty(self):
        stdout, rc = _ptd._run_handler(
            ["/no/such/interp", "/no/such/script.py"], "{}"
        )
        assert stdout == ""
        assert rc == 0


# ---------------------------------------------------------------------------
# _skip_names(): tested via subprocess with env injection
# ---------------------------------------------------------------------------

class TestSkipNamesViaSubprocess:
    """Test _skip_names() behaviour by running the dispatcher with SKIP env var."""

    def test_skip_write_guard_passes_blocked_write(self):
        """Skipping write-guard allows a write that would otherwise be blocked."""
        block_event = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test_foo.py", "content": _MOCK_CONTENT},
        }
        out, rc = _run_script(
            PRETOOLUSE_DISPATCHER,
            block_event,
            env={"CT_PRETOOLUSE_DISPATCHER_SKIP": "write-guard.py"},
        )
        assert rc == 0
        assert '"decision": "block"' not in out

    def test_skip_git_safety_guard_passes_blocked_bash(self):
        """Skipping git-safety-guard allows a git add -A that would otherwise block."""
        block_event = {"tool_name": "Bash", "tool_input": {"command": "git add -A"}}
        out, rc = _run_script(
            PRETOOLUSE_DISPATCHER,
            block_event,
            env={"CT_PRETOOLUSE_DISPATCHER_SKIP": "git-safety-guard.py,rtk"},
        )
        assert rc == 0
        assert '"decision": "block"' not in out


# ---------------------------------------------------------------------------
# Acceptance tests: blocking-guard verbatim contract
# ---------------------------------------------------------------------------

class TestWriteGuardBlock:
    """Test 1: write-guard BLOCK verbatim contract (exit-code + output diffs)."""

    @pytest.fixture
    def block_event(self):
        return {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test_foo.py", "content": _MOCK_CONTENT},
        }

    def test_exit_codes_match(self, block_event):
        _, guard_rc = _run_script(WRITE_GUARD, block_event)
        _, disp_rc = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        assert guard_rc == disp_rc, f"exit code mismatch: guard={guard_rc} disp={disp_rc}"

    def test_stdout_verbatim_identical(self, block_event):
        guard_out, _ = _run_script(WRITE_GUARD, block_event)
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        assert guard_out == disp_out, (
            f"Dispatcher output is NOT verbatim-identical to guard output:\n"
            f"  guard:      {guard_out!r}\n"
            f"  dispatcher: {disp_out!r}"
        )

    def test_decision_is_block(self, block_event):
        guard_out, _ = _run_script(WRITE_GUARD, block_event)
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        assert json.loads(guard_out)["decision"] == "block"
        assert json.loads(disp_out)["decision"] == "block"

    def test_block_reason_mentions_mock(self, block_event):
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        reason = json.loads(disp_out).get("reason", "")
        assert "Mock" in reason or "mock" in reason


class TestWriteGuardAllow:
    """Test 2: write-guard ALLOW — benign Write event."""

    @pytest.fixture
    def allow_event(self):
        return {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/regular_file.py",
                "content": "def foo():\n    return 1\n",
            },
        }

    def test_guard_allows_exit_0(self, allow_event):
        _, guard_rc = _run_script(WRITE_GUARD, allow_event)
        assert guard_rc == 0

    def test_guard_no_block_decision(self, allow_event):
        guard_out, _ = _run_script(WRITE_GUARD, allow_event)
        assert '"decision": "block"' not in guard_out

    def test_dispatcher_allows_exit_0(self, allow_event):
        _, disp_rc = _run_script(PRETOOLUSE_DISPATCHER, allow_event)
        assert disp_rc == 0

    def test_dispatcher_no_block_decision(self, allow_event):
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, allow_event)
        assert '"decision": "block"' not in disp_out


class TestGitSafetyGuardBlock:
    """Test 3: git-safety-guard BLOCK verbatim contract (exit-code + output diffs)."""

    @pytest.fixture
    def block_event(self):
        return {"tool_name": "Bash", "tool_input": {"command": "git add -A"}}

    def test_exit_codes_match(self, block_event):
        _, guard_rc = _run_script(GIT_SAFETY_GUARD, block_event)
        _, disp_rc = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        assert guard_rc == disp_rc, f"exit code mismatch: guard={guard_rc} disp={disp_rc}"

    def test_stdout_verbatim_identical(self, block_event):
        guard_out, _ = _run_script(GIT_SAFETY_GUARD, block_event)
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        assert guard_out == disp_out, (
            f"Dispatcher output is NOT verbatim-identical to guard output:\n"
            f"  guard:      {guard_out!r}\n"
            f"  dispatcher: {disp_out!r}"
        )

    def test_decision_is_block(self, block_event):
        guard_out, _ = _run_script(GIT_SAFETY_GUARD, block_event)
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        assert json.loads(guard_out)["decision"] == "block"
        assert json.loads(disp_out)["decision"] == "block"

    def test_block_reason_mentions_broad_add(self, block_event):
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, block_event)
        reason = json.loads(disp_out).get("reason", "")
        assert "git add" in reason.lower() or "BLOCKED" in reason


class TestGitSafetyGuardAllow:
    """Test 4: git-safety-guard ALLOW — benign Bash.

    Note: rtk hook claude may legitimately produce a command-rewrite response
    for benign commands. 'Pass through' means not blocked — not zero output.
    """

    @pytest.fixture
    def allow_event(self):
        return {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}

    def test_guard_allows_exit_0(self, allow_event):
        _, guard_rc = _run_script(GIT_SAFETY_GUARD, allow_event)
        assert guard_rc == 0

    def test_guard_no_block(self, allow_event):
        guard_out, _ = _run_script(GIT_SAFETY_GUARD, allow_event)
        assert '"decision": "block"' not in guard_out

    def test_dispatcher_not_blocked_exit_0(self, allow_event):
        _, disp_rc = _run_script(PRETOOLUSE_DISPATCHER, allow_event)
        assert disp_rc == 0

    def test_dispatcher_no_block_decision(self, allow_event):
        disp_out, _ = _run_script(PRETOOLUSE_DISPATCHER, allow_event)
        assert '"decision": "block"' not in disp_out


class TestCodesightPromptInjection:
    """Test 6: Agent PreToolUse gets CODESIGHT_INSTRUCTION injected."""

    @pytest.fixture
    def agent_event(self):
        return {
            "tool_name": "Agent",
            "tool_input": {"prompt": "implement a function to process data"},
        }

    def test_exits_0(self, agent_event):
        _, rc = _run_script(PRETOOLUSE_DISPATCHER, agent_event)
        assert rc == 0

    def test_stdout_is_json(self, agent_event):
        out, _ = _run_script(PRETOOLUSE_DISPATCHER, agent_event)
        parsed = json.loads(out)
        assert isinstance(parsed, dict)

    def test_codesight_instruction_injected(self, agent_event):
        out, _ = _run_script(PRETOOLUSE_DISPATCHER, agent_event)
        parsed = json.loads(out)
        hook_out = parsed.get("hookSpecificOutput", {})
        updated = hook_out.get("updatedInput", {})
        injected_prompt = updated.get("prompt", "")
        assert "MANDATORY SEARCH RULES" in injected_prompt

    def test_permission_decision_is_allow(self, agent_event):
        out, _ = _run_script(PRETOOLUSE_DISPATCHER, agent_event)
        parsed = json.loads(out)
        hook_out = parsed.get("hookSpecificOutput", {})
        assert hook_out.get("permissionDecision") == "allow"


class TestDisableEscapeHatch:
    """Test: CT_PRETOOLUSE_DISPATCHER_DISABLE=1 bypasses everything."""

    def test_disable_blocks_blocked_write(self):
        """Even a would-be-blocked Write is allowed when dispatcher is disabled."""
        block_event = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/test_foo.py", "content": _MOCK_CONTENT},
        }
        result = subprocess.run(
            [sys.executable, str(PRETOOLUSE_DISPATCHER)],
            input=json.dumps(block_event),
            capture_output=True,
            text=True,
            timeout=10,
            env={
                **os.environ,
                "CT_PRETOOLUSE_DISPATCHER_DISABLE": "1",
                "WRITE_GUARD_ALLOW_INSTRUCTION_EDIT": "",
                "WRITE_GUARD_ALLOW_MIGRATION_EDIT": "",
            },
        )
        assert result.returncode == 0
        assert result.stdout == ""

    def test_disable_blocks_blocked_bash(self):
        block_bash = {"tool_name": "Bash", "tool_input": {"command": "git add -A"}}
        result = subprocess.run(
            [sys.executable, str(PRETOOLUSE_DISPATCHER)],
            input=json.dumps(block_bash),
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "CT_PRETOOLUSE_DISPATCHER_DISABLE": "1"},
        )
        assert result.returncode == 0
        assert result.stdout == ""


class TestUnknownToolName:
    def test_unknown_tool_exits_0_no_output(self):
        event = {"tool_name": "UnknownTool", "tool_input": {}}
        out, rc = _run_script(PRETOOLUSE_DISPATCHER, event)
        assert rc == 0
        assert out.strip() == ""

    def test_empty_tool_name_exits_0(self):
        event = {"tool_name": "", "tool_input": {}}
        out, rc = _run_script(PRETOOLUSE_DISPATCHER, event)
        assert rc == 0
        assert out.strip() == ""
