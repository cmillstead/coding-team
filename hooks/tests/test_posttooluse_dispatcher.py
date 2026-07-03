"""Tests for posttooluse-dispatcher.py.

Acceptance tests that verify the consolidation invariants:
  1. codesight query logging: mcp__codesight__query → TSV line appended to usage.log.
  2. loop-detection: Bash PostToolUse passes through without crash.
  3. lint-warning-enforcer: Bash with lint warnings → advisory emitted.
  4. coding-team-lifecycle: non-coding-team Skill passes through silently.
  5. builder-self-check: Write PostToolUse no crash.
  6. Multiple-handler merging: both loop-detection and lint-warning-enforcer
     advisories are combined into one response.
  7. Disable escape hatch: CT_POSTTOOLUSE_DISPATCHER_DISABLE=1 → exit 0 no output.
  8. Unknown tool name: exits 0 silently.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/
POSTTOOLUSE_DISPATCHER = HOOKS_DIR / "posttooluse-dispatcher.py"
USAGE_LOG = Path.home() / ".config" / "codesight-mcp" / "usage.log"

# Load dispatcher module for unit tests
_spec = importlib.util.spec_from_file_location("pod", POSTTOOLUSE_DISPATCHER)
_pod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pod)


def _run_script(
    script: Path,
    event: dict,
    env: dict | None = None,
) -> tuple[str, int]:
    """Run hook script via subprocess with event on stdin. Return (stdout, returncode)."""
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=20,
        env=merged_env,
    )
    return result.stdout, result.returncode


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------

class TestClassifyOutput:
    def test_empty_string_returns_empty(self):
        assert _pod._classify_output("") == ("", "")

    def test_whitespace_only_returns_empty(self):
        assert _pod._classify_output("   \n  ") == ("", "")

    def test_block_decision_classified(self):
        raw = json.dumps({"decision": "block", "reason": "BLOCKED: test"})
        kind, content = _pod._classify_output(raw)
        assert kind == "block"
        assert content == "BLOCKED: test"

    def test_advisory_classified(self):
        raw = json.dumps({"decision": "allow", "reason": "Some warning"})
        kind, content = _pod._classify_output(raw)
        assert kind == "advisory"
        assert content == "Some warning"

    def test_allow_with_no_reason_returns_empty(self):
        raw = json.dumps({"decision": "allow"})
        kind, content = _pod._classify_output(raw)
        assert kind == ""
        assert content == ""

    def test_malformed_json_returns_empty(self):
        assert _pod._classify_output("{not valid}") == ("", "")

    def test_unknown_json_shape_returns_empty(self):
        assert _pod._classify_output('{"something": "else"}') == ("", "")


class TestRunHandler:
    def test_silent_script_returns_empty(self, tmp_path):
        script = tmp_path / "silent.py"
        script.write_text("import sys\nsys.exit(0)\n")
        stdout, stderr, rc = _pod._run_handler([sys.executable, str(script)], "{}")
        assert stdout == ""
        assert rc == 0

    def test_output_propagated(self, tmp_path):
        script = tmp_path / "output.py"
        script.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"warn"}))\n'
        )
        stdout, stderr, rc = _pod._run_handler([sys.executable, str(script)], "{}")
        assert '"decision"' in stdout

    def test_crash_returns_empty_stdout(self, tmp_path):
        crash = tmp_path / "crash.py"
        crash.write_text("raise RuntimeError('boom')\n")
        stdout, stderr, rc = _pod._run_handler([sys.executable, str(crash)], "{}")
        assert stdout == ""
        # rc reflects the subprocess exit code (non-zero on crash);
        # isolation is at routing level: empty stdout means dispatcher skips.

    def test_stderr_captured(self, tmp_path):
        """Handler stderr is captured and returned as the second element."""
        script = tmp_path / "stderr_writer.py"
        script.write_text(
            'import sys\nsys.stderr.write("blocked via exit 2")\nsys.exit(2)\n'
        )
        stdout, stderr, rc = _pod._run_handler([sys.executable, str(script)], "{}")
        assert stdout == ""
        assert "blocked via exit 2" in stderr
        assert rc == 2


class TestRunAndEmit:
    """Unit tests for _run_and_emit output merging logic."""

    def test_all_silent_produces_no_output(self, tmp_path, capsys):
        silent = tmp_path / "silent.py"
        silent.write_text("import sys\nsys.exit(0)\n")
        _pod._run_and_emit([str(silent)], "{}", set())
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_single_advisory_emitted(self, tmp_path, capsys):
        advisor = tmp_path / "advisor.py"
        advisor.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"Warning A"}))\n'
        )
        _pod._run_and_emit([str(advisor)], "{}", set())
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["decision"] == "allow"
        assert "Warning A" in parsed["reason"]

    def test_two_advisories_merged(self, tmp_path, capsys):
        a = tmp_path / "a.py"
        a.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"Warning A"}))\n'
        )
        b = tmp_path / "b.py"
        b.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"Warning B"}))\n'
        )
        _pod._run_and_emit([str(a), str(b)], "{}", set())
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["decision"] == "allow"
        assert "Warning A" in parsed["reason"]
        assert "Warning B" in parsed["reason"]

    def test_block_takes_priority_over_advisory(self, tmp_path, capsys):
        advisor = tmp_path / "advisor.py"
        advisor.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"Warning"}))\n'
        )
        blocker = tmp_path / "blocker.py"
        blocker.write_text(
            'import json\nprint(json.dumps({"decision":"block","reason":"BLOCKED"}))\n'
        )
        _pod._run_and_emit([str(advisor), str(blocker)], "{}", set())
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["decision"] == "block"
        assert "BLOCKED" in parsed["reason"]

    def test_skipped_handler_not_run(self, tmp_path, capsys):
        blocker = tmp_path / "blocker.py"
        blocker.write_text(
            'import json\nprint(json.dumps({"decision":"block","reason":"BLOCKED"}))\n'
        )
        _pod._run_and_emit([str(blocker)], "{}", {"blocker.py"})
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_exit2_block_raises_systemexit_2(self, tmp_path, capsys):
        """Handler exiting with code 2 causes dispatcher to sys.exit(2)."""
        exit2 = tmp_path / "exit2.py"
        exit2.write_text(
            'import sys\nsys.stderr.write("blocked via exit 2")\nsys.exit(2)\n'
        )
        with pytest.raises(SystemExit) as exc_info:
            _pod._run_and_emit([str(exit2)], "{}", set())
        assert exc_info.value.code == 2

    def test_exit2_stderr_forwarded(self, tmp_path, capsys):
        """Handler exit-2 stderr is written to the dispatcher's real stderr."""
        exit2 = tmp_path / "exit2.py"
        exit2.write_text(
            'import sys\nsys.stderr.write("blocked via exit 2\\n")\nsys.exit(2)\n'
        )
        with pytest.raises(SystemExit):
            _pod._run_and_emit([str(exit2)], "{}", set())
        captured = capsys.readouterr()
        assert "blocked via exit 2" in captured.err

    def test_exit2_first_handler_wins_remaining_not_run(self, tmp_path, capsys):
        """First exit-2 handler wins; subsequent handlers are not executed."""
        exit2 = tmp_path / "exit2.py"
        exit2.write_text(
            'import sys\nsys.stderr.write("first block")\nsys.exit(2)\n'
        )
        # Second handler would emit a stdout-JSON block if reached.
        second = tmp_path / "second.py"
        second.write_text(
            'import json\nprint(json.dumps({"decision":"block","reason":"SECOND"}))\n'
        )
        with pytest.raises(SystemExit) as exc_info:
            _pod._run_and_emit([str(exit2), str(second)], "{}", set())
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "first block" in captured.err
        # The second handler's stdout-JSON must NOT appear
        assert "SECOND" not in captured.out

    def test_exit2_takes_priority_over_stdout_json_advisory(self, tmp_path, capsys):
        """Exit-2 handler takes priority when it appears after an advisory."""
        advisor = tmp_path / "advisor.py"
        advisor.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"advisory"}))\n'
        )
        exit2 = tmp_path / "exit2.py"
        exit2.write_text(
            'import sys\nsys.stderr.write("exit2 block")\nsys.exit(2)\n'
        )
        with pytest.raises(SystemExit) as exc_info:
            _pod._run_and_emit([str(advisor), str(exit2)], "{}", set())
        assert exc_info.value.code == 2

    def test_stdout_json_block_still_emits_json_exit0(self, tmp_path, capsys):
        """Stdout-JSON block (mechanism a) still emits JSON and exits 0."""
        blocker = tmp_path / "blocker.py"
        blocker.write_text(
            'import json\nprint(json.dumps({"decision":"block","reason":"BLOCKED"}))\n'
        )
        _pod._run_and_emit([str(blocker)], "{}", set())
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["decision"] == "block"
        assert "BLOCKED" in parsed["reason"]

    def test_advisories_still_merge_when_no_exit2(self, tmp_path, capsys):
        """Multiple advisories still merge when no handler exits 2."""
        a = tmp_path / "a.py"
        a.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"Warning A"}))\n'
        )
        b = tmp_path / "b.py"
        b.write_text(
            'import json\nprint(json.dumps({"decision":"allow","reason":"Warning B"}))\n'
        )
        _pod._run_and_emit([str(a), str(b)], "{}", set())
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["decision"] == "allow"
        assert "Warning A" in parsed["reason"]
        assert "Warning B" in parsed["reason"]


# ---------------------------------------------------------------------------
# Acceptance tests (subprocess)
# ---------------------------------------------------------------------------

class TestCodesightQueryLogging:
    """Test 5: mcp__codesight__query PostToolUse → usage.log TSV appended."""

    @pytest.fixture
    def query_event(self):
        return {
            "tool_name": "mcp__codesight__query",
            "tool_input": {
                "operation": "search-symbols",
                "params": {"repo": "test-repo", "query": "dispatcher"},
            },
            "tool_result": {},
        }

    def test_dispatcher_exits_0(self, query_event):
        _, rc = _run_script(POSTTOOLUSE_DISPATCHER, query_event)
        assert rc == 0

    def test_usage_log_grows(self, query_event):
        try:
            before = USAGE_LOG.stat().st_size
        except FileNotFoundError:
            before = 0
        _run_script(POSTTOOLUSE_DISPATCHER, query_event)
        after = USAGE_LOG.stat().st_size
        assert after > before

    def test_logged_line_is_tsv_with_5_fields(self, query_event):
        _run_script(POSTTOOLUSE_DISPATCHER, query_event)
        lines = USAGE_LOG.read_text().splitlines()
        last = lines[-1]
        fields = last.split("\t")
        assert len(fields) == 5, f"Expected 5 TSV fields, got {len(fields)}: {last!r}"

    def test_logged_line_contains_operation(self, query_event):
        _run_script(POSTTOOLUSE_DISPATCHER, query_event)
        last = USAGE_LOG.read_text().splitlines()[-1]
        assert "search-symbols" in last


class TestLoopDetection:
    """Test 7a: loop-detection — Bash PostToolUse no crash."""

    @pytest.fixture
    def bash_post_event(self):
        return {
            "tool_name": "Bash",
            "tool_input": {"command": "npm test"},
            "tool_result": {
                "exit_code": 1,
                "stdout": "FAIL: test failed",
                "stderr": "Error: test failed",
            },
        }

    def test_exits_0(self, bash_post_event, tmp_state_dir):
        _, rc = _run_script(POSTTOOLUSE_DISPATCHER, bash_post_event)
        assert rc == 0


class TestLintWarningEnforcer:
    """Test 7b: lint-warning-enforcer — advisory on lint warnings."""

    @pytest.fixture
    def lint_event(self):
        return {
            "tool_name": "Bash",
            "tool_input": {"command": "eslint src/"},
            "tool_result": {
                "exit_code": 1,
                "stdout": "warning: unused variable 'x'",
                "stderr": "",
            },
        }

    def test_exits_0(self, lint_event):
        _, rc = _run_script(POSTTOOLUSE_DISPATCHER, lint_event)
        assert rc == 0

    def test_advisory_emitted_for_warnings(self, lint_event):
        out, _ = _run_script(POSTTOOLUSE_DISPATCHER, lint_event)
        assert out.strip(), "Expected advisory output for warnings"
        parsed = json.loads(out)
        assert parsed["decision"] == "allow"
        assert "warning" in parsed["reason"].lower()


class TestCodingTeamLifecycle:
    """Test 7c: coding-team-lifecycle — non-coding-team Skill passes through."""

    @pytest.fixture
    def non_ct_skill_event(self):
        return {
            "tool_name": "Skill",
            "tool_input": {"skill": "some-other-skill"},
            "tool_result": {"success": True},
        }

    def test_exits_0(self, non_ct_skill_event):
        _, rc = _run_script(POSTTOOLUSE_DISPATCHER, non_ct_skill_event)
        assert rc == 0

    def test_silent_for_non_ct_skill(self, non_ct_skill_event):
        out, _ = _run_script(POSTTOOLUSE_DISPATCHER, non_ct_skill_event)
        assert '"decision": "block"' not in out


class TestBuilderSelfCheck:
    """Test 7d: builder-self-check — Write PostToolUse no crash."""

    @pytest.fixture
    def write_post_event(self):
        return {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/test_acceptance_builder.py",
                "content": "def foo(): pass\n",
            },
            "tool_result": {"success": True},
        }

    def test_exits_0(self, write_post_event):
        _, rc = _run_script(POSTTOOLUSE_DISPATCHER, write_post_event)
        assert rc == 0

    def test_no_block_decision(self, write_post_event):
        out, _ = _run_script(POSTTOOLUSE_DISPATCHER, write_post_event)
        assert '"decision": "block"' not in out


class TestDisableEscapeHatch:
    """CT_POSTTOOLUSE_DISPATCHER_DISABLE=1 bypasses all handlers."""

    def test_disable_produces_no_output(self):
        query_event = {
            "tool_name": "mcp__codesight__query",
            "tool_input": {"operation": "search-symbols", "params": {"repo": "x"}},
            "tool_result": {},
        }
        result = subprocess.run(
            [sys.executable, str(POSTTOOLUSE_DISPATCHER)],
            input=json.dumps(query_event),
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "CT_POSTTOOLUSE_DISPATCHER_DISABLE": "1"},
        )
        assert result.returncode == 0
        assert result.stdout == ""


class TestUnknownToolName:
    def test_unknown_tool_exits_0_no_output(self):
        event = {"tool_name": "UnknownTool", "tool_input": {}, "tool_result": {}}
        out, rc = _run_script(POSTTOOLUSE_DISPATCHER, event)
        assert rc == 0
        assert out.strip() == ""

    def test_mcp_non_codesight_exits_0(self):
        event = {
            "tool_name": "mcp__some_other_tool",
            "tool_input": {},
            "tool_result": {},
        }
        out, rc = _run_script(POSTTOOLUSE_DISPATCHER, event)
        assert rc == 0
        assert out.strip() == ""
