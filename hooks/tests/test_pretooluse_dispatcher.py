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

HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/
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
    cwd: str | None = None,
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
        cwd=cwd,
    )
    return result.stdout, result.returncode


def _provision_home_under_src(tmp_path: Path) -> Path:
    """Provision a hermetic HOME under tmp_path for dispatcher Agent-path tests.

    codesight-hooks.py injects the mandatory-codesight directive only when cwd is
    under ~/src/ (it reads SRC_PREFIX from HOME), so to exercise the injection the
    dispatcher must run with HOME=tmp_path and cwd under tmp_path/src. But the
    dispatcher also resolves its sibling hooks via HOME/.claude/hooks, so that dir
    must contain the real handler scripts — symlink it to the source hooks dir.
    Returns the tmp_path/src/proj path to use as cwd (callers set HOME=tmp_path).
    """
    proj = tmp_path / "src" / "proj"
    proj.mkdir(parents=True)
    claude_hooks = tmp_path / ".claude" / "hooks"
    claude_hooks.parent.mkdir(parents=True)
    claude_hooks.symlink_to(HOOKS_DIR)
    return proj


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
        stdout, stderr, rc = _ptd._run_handler([sys.executable, str(script)], "{}")
        assert stdout == ""
        assert rc == 0

    def test_output_script_returns_output(self, tmp_path):
        script = tmp_path / "output.py"
        script.write_text(
            'import json\nprint(json.dumps({"decision":"block","reason":"test"}))\n'
        )
        stdout, stderr, rc = _ptd._run_handler([sys.executable, str(script)], "{}")
        assert '"decision"' in stdout

    def test_crashing_script_returns_empty_stdout(self, tmp_path):
        crash = tmp_path / "crash.py"
        crash.write_text("raise RuntimeError('boom')\n")
        stdout, stderr, rc = _ptd._run_handler([sys.executable, str(crash)], "{}")
        assert stdout == ""
        # rc reflects the subprocess exit code (non-zero on crash);
        # isolation is at routing level: empty stdout means dispatcher skips.

    def test_timeout_returns_empty(self, tmp_path):
        slow = tmp_path / "slow.py"
        slow.write_text("import time\ntime.sleep(10)\n")
        stdout, stderr, rc = _ptd._run_handler(
            [sys.executable, str(slow)], "{}", timeout=1
        )
        assert stdout == ""
        assert rc == 0

    def test_missing_interpreter_returns_empty(self):
        stdout, stderr, rc = _ptd._run_handler(
            ["/no/such/interp", "/no/such/script.py"], "{}"
        )
        assert stdout == ""
        assert rc == 0

    def test_stderr_is_captured(self, tmp_path):
        """Handler stderr is captured and returned as the second element."""
        script = tmp_path / "stderr_writer.py"
        script.write_text(
            'import sys\nsys.stderr.write("blocked via stderr")\nsys.exit(2)\n'
        )
        stdout, stderr, rc = _ptd._run_handler([sys.executable, str(script)], "{}")
        assert stdout == ""
        assert "blocked via stderr" in stderr
        assert rc == 2

    def test_exit2_returncode_captured(self, tmp_path):
        """Handler exiting with code 2 returns rc=2."""
        script = tmp_path / "exit2.py"
        script.write_text("import sys\nsys.exit(2)\n")
        stdout, stderr, rc = _ptd._run_handler([sys.executable, str(script)], "{}")
        assert rc == 2


class TestPassthrough:
    """Unit tests for _passthrough: stdout, stderr forwarding and exit code."""

    def test_exits_with_given_returncode(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            _ptd._passthrough("", "", 2)
        assert exc_info.value.code == 2

    def test_stdout_written_verbatim(self, capsys):
        payload = '{"decision":"block","reason":"BLOCKED"}\n'
        with pytest.raises(SystemExit):
            _ptd._passthrough(payload, "", 0)
        captured = capsys.readouterr()
        assert captured.out == payload

    def test_stderr_written_verbatim(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            _ptd._passthrough("", "blocked via exit 2\n", 2)
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "blocked via exit 2" in captured.err

    def test_empty_stderr_produces_no_stderr_output(self, capsys):
        payload = '{"decision":"block","reason":"BLOCKED"}\n'
        with pytest.raises(SystemExit):
            _ptd._passthrough(payload, "", 0)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_both_stdout_and_stderr_forwarded(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            _ptd._passthrough("stdout-content\n", "stderr-content\n", 2)
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "stdout-content" in captured.out
        assert "stderr-content" in captured.err


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

    def test_codesight_instruction_injected(self, agent_event, tmp_path):
        # The codesight directive is only injected when cwd is under ~/src/;
        # run inside a tmp ~/src (HOME=tmp_path) so the injection fires.
        proj = _provision_home_under_src(tmp_path)
        out, _ = _run_script(
            PRETOOLUSE_DISPATCHER, agent_event,
            env={"HOME": str(tmp_path)}, cwd=str(proj),
        )
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


class TestAgentGuardChaining:
    """Path B: paul-apply-agent-guard runs FIRST in the Agent branch. If it
    blocks, its block is passed through and codesight does NOT run. If it does
    not block, codesight injection still happens."""

    def test_agent_guard_block_passes_through(self, tmp_path):
        """An execution-intent Agent dispatch for a PLAN with no PASS is blocked
        by the dispatcher (guard output, not codesight injection).

        Run inside a hermetic ~/src (cwd under tmp_path/src) so the codesight
        cwd-gate WOULD allow injection: that makes the secondary assertion below
        isolate the guard short-circuit as the ONLY reason the directive is
        absent. Outside ~/src the gate would suppress the directive regardless,
        rendering that assertion vacuous.
        """
        proj = _provision_home_under_src(tmp_path)
        sub = proj / ".paul" / "phases" / "02-medium-risk-domains"
        sub.mkdir(parents=True)
        plan = sub / "02-02-PLAN.md"
        plan.write_bytes(b"plan body\n")  # no .review.json
        rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
        event = {
            "tool_name": "Agent",
            "tool_input": {"prompt": f"Implement Task 1 from {rel}. Write code."},
        }
        result = subprocess.run(
            [sys.executable, str(PRETOOLUSE_DISPATCHER)],
            input=json.dumps(event), capture_output=True, text=True,
            timeout=20, cwd=str(proj), env={**os.environ, "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") == "block"
        # codesight injection must NOT be present (guard short-circuited).
        # cwd is under ~/src, so the cwd-gate would ALLOW injection — the only
        # reason the directive is absent is the guard's short-circuit.
        assert "MANDATORY SEARCH RULES" not in result.stdout

    def test_agent_non_execution_falls_through_to_codesight(self, tmp_path):
        """A benign Agent dispatch (no plan execution) still gets codesight
        injection — the guard is silent and the chain falls through. The
        directive is only injected under ~/src/, so run inside a tmp ~/src."""
        proj = _provision_home_under_src(tmp_path)
        event = {
            "tool_name": "Agent",
            "tool_input": {"prompt": "implement a function to process data"},
        }
        result = subprocess.run(
            [sys.executable, str(PRETOOLUSE_DISPATCHER)],
            input=json.dumps(event), capture_output=True, text=True,
            timeout=20, cwd=str(proj), env={**os.environ, "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed.get("decision") != "block"
        hook_out = parsed.get("hookSpecificOutput", {})
        injected = hook_out.get("updatedInput", {}).get("prompt", "")
        assert "MANDATORY SEARCH RULES" in injected


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


# ---------------------------------------------------------------------------
# Engram delivery injector wiring (TRK-209)
# ---------------------------------------------------------------------------

def _fake_engram_high(tmp_path):
    import stat as _stat
    b = tmp_path / "engram"
    b.write_text("#!/usr/bin/env python3\n"
                 "import json; print(json.dumps({'file':'/f','query':'q',"
                 "'items':[{'id':1,'title':'HITBLOCK','score':0.48}],'count':1}))\n")
    b.chmod(b.stat().st_mode | _stat.S_IEXEC | _stat.S_IRUSR)
    return b


def _dedup_file_for(session_id):
    """GLOBAL /tmp dedup path for a subprocess run under session_id (mirrors
    _lib.state.get_state_file + engram-pretool-inject.DEDUP_PREFIX). Lets wiring tests
    clean up so dedup state never poisons a rerun."""
    import hashlib
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return Path(f"/tmp/engram-delivery-dedup-{h}.json")


def _uid(prefix):
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def test_read_event_injects_engram_block(tmp_path):
    fake = _fake_engram_high(tmp_path)
    sid = _uid("disp-read")
    try:
        env = {"ENGRAM_PRETOOL_BIN": str(fake), "ENGRAM_DELIVERY_LOG": str(tmp_path / "d.jsonl"),
               "CLAUDE_CODE_SESSION_ID": sid,
               "ENGRAM_PRETOOL_INJECT_TIMEOUT_S": "10"}  # fake engram is a slow Python cold-start under load
        out, rc = _run_script(PRETOOLUSE_DISPATCHER, {"tool_name": "Read",
                              "tool_input": {"file_path": "/f.py"}}, env=env)
        assert rc == 0
        assert "HITBLOCK" in out
        assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    finally:
        _dedup_file_for(sid).unlink(missing_ok=True)


def test_write_injects_after_write_guard_is_silent(tmp_path):
    fake = _fake_engram_high(tmp_path)
    sid = _uid("disp-write")
    try:
        env = {"ENGRAM_PRETOOL_BIN": str(fake), "ENGRAM_DELIVERY_LOG": str(tmp_path / "d.jsonl"),
               "CLAUDE_CODE_SESSION_ID": sid,
               "ENGRAM_PRETOOL_INJECT_TIMEOUT_S": "10"}  # fake engram is a slow Python cold-start under load
        # A benign Write to a NON-instruction file in /tmp: write-guard + clean-tree stay silent.
        out, rc = _run_script(PRETOOLUSE_DISPATCHER, {"tool_name": "Write",
                              "tool_input": {"file_path": str(tmp_path / "note.txt"),
                                             "content": "hello"}}, env=env)
        assert rc == 0
        assert "HITBLOCK" in out
    finally:
        _dedup_file_for(sid).unlink(missing_ok=True)


def test_blocked_write_does_not_inject(tmp_path):
    """write-guard BLOCK must own the response; injector must NOT run/emit after a block."""
    fake = _fake_engram_high(tmp_path)
    env = {"ENGRAM_PRETOOL_BIN": str(fake), "ENGRAM_DELIVERY_LOG": str(tmp_path / "d.jsonl"),
           "CLAUDE_CODE_SESSION_ID": _uid("disp-blk"),
           "ENGRAM_PRETOOL_INJECT_TIMEOUT_S": "10"}  # fake engram is a slow Python cold-start under load
    # _MOCK_CONTENT triggers write-guard's no-mocks BLOCK (see top of this file).
    out, rc = _run_script(PRETOOLUSE_DISPATCHER, {"tool_name": "Write",
                          "tool_input": {"file_path": str(tmp_path / "test_x.py"),
                                         "content": _MOCK_CONTENT}}, env=env, cwd=str(tmp_path))
    assert "HITBLOCK" not in out            # injector suppressed by first-response-wins
    assert '"decision"' in out or rc == 2   # the block is what surfaced


def test_injector_failure_does_not_break_read_dispatch(tmp_path):
    """A dead engram binary must leave Read dispatch at exit 0, no output."""
    env = {"ENGRAM_PRETOOL_BIN": "/no/such/engram",
           "ENGRAM_DELIVERY_LOG": str(tmp_path / "d.jsonl"),
           "CLAUDE_CODE_SESSION_ID": _uid("disp-x")}
    out, rc = _run_script(PRETOOLUSE_DISPATCHER, {"tool_name": "Read",
                          "tool_input": {"file_path": "/f.py"}}, env=env)
    assert rc == 0
    assert out.strip() == ""


def test_injector_nonzero_exit_is_swallowed(tmp_path):
    """An injector CRASH (import/syntax error → nonzero exit BEFORE its own __main__
    try/except) must NOT become the dispatcher's exit code — otherwise every Read/Edit/
    Write would fail. Point CT_ENGRAM_INJECT_PATH at a fake injector that exits 3; the
    Read dispatch must still exit 0 with empty stdout."""
    import stat as _stat
    crash = tmp_path / "crash_injector.py"
    crash.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(3)\n")
    crash.chmod(crash.stat().st_mode | _stat.S_IEXEC | _stat.S_IRUSR)
    env = {"CT_ENGRAM_INJECT_PATH": str(crash),
           "ENGRAM_DELIVERY_LOG": str(tmp_path / "d.jsonl"),
           "CLAUDE_CODE_SESSION_ID": _uid("disp-crash")}
    out, rc = _run_script(PRETOOLUSE_DISPATCHER, {"tool_name": "Read",
                          "tool_input": {"file_path": "/f.py"}}, env=env)
    assert rc == 0            # crash swallowed, not forwarded
    assert out.strip() == ""


def test_injector_nonzero_exit_is_swallowed_on_write(tmp_path):
    """Same crash-swallow guarantee as the Read-branch test, but for the Edit|Write
    branch (identical swallow logic, previously untested). After a SILENT write-guard on
    a benign Write, a crashing injector (nonzero exit) must NOT become the dispatcher's
    exit code — otherwise every Edit/Write would fail. Point CT_ENGRAM_INJECT_PATH at a
    fake injector that exits 3; the Write dispatch must still exit 0 with empty stdout."""
    import stat as _stat
    crash = tmp_path / "crash_injector.py"
    crash.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(3)\n")
    crash.chmod(crash.stat().st_mode | _stat.S_IEXEC | _stat.S_IRUSR)
    env = {"CT_ENGRAM_INJECT_PATH": str(crash),
           "ENGRAM_DELIVERY_LOG": str(tmp_path / "d.jsonl"),
           "CLAUDE_CODE_SESSION_ID": _uid("disp-crash-write")}
    # Benign Write to a NON-instruction file in /tmp: clean-tree + write-guard stay silent.
    out, rc = _run_script(PRETOOLUSE_DISPATCHER, {"tool_name": "Write",
                          "tool_input": {"file_path": str(tmp_path / "note.txt"),
                                         "content": "hello"}}, env=env)
    assert rc == 0            # crash swallowed on the Write branch, not forwarded
    assert out.strip() == ""
