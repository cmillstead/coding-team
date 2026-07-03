"""Tests for loop-detection.py hook."""

import hashlib
from pathlib import Path


def _state_file_for_session(session_id: str) -> Path:
    """Compute the state file path for a given session ID (mirrors _lib/state.py logic)."""
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return Path(f"/tmp/claude-loop-detection-{session_hash}.json")


class TestConditionalSaveState:
    def test_success_with_no_matching_failures_does_not_write_state(
        self, run_hook, make_event, tmp_state_dir
    ):
        """A passing command with an empty/unrelated failure list must not rewrite state."""
        session_id = tmp_state_dir
        state_path = _state_file_for_session(session_id)

        # Ensure state file does not exist before the call
        state_path.unlink(missing_ok=True)

        event = make_event(
            "Bash",
            command="echo ok",
            tool_result={"exit_code": 0, "stdout": "ok", "stderr": ""},
        )
        run_hook("loop-detection.py", event)

        # State file must still be absent — no-op save must not create it
        assert not state_path.exists(), (
            f"State file {state_path} was written on a successful command "
            "with no matching failures, but should have been skipped."
        )


class TestNonBashTool:
    def test_non_bash_tool_produces_no_output(self, run_hook, make_event):
        event = make_event("Edit", file_path="/src/main.py")
        result = run_hook("loop-detection.py", event)
        assert result.stdout.strip() == ""
        assert result.returncode == 0


class TestSingleFailure:
    def test_single_failure_no_advisory(self, run_hook, make_event, tmp_state_dir):
        """A single failure should not trigger recovery — under MAX_RETRIES threshold."""
        event = make_event(
            "Bash",
            command="npm run build",
            tool_result={"stdout": "Build failed: module not found", "stderr": "", "exit_code": 1},
        )
        result = run_hook("loop-detection.py", event)
        # Single failure: under threshold, no advisory
        assert result.parsed is None or "recovery" not in (result.parsed or {}).get("reason", "").lower()


class TestSuccessfulCommand:
    def test_successful_command_no_advisory(self, run_hook, make_event, tmp_state_dir):
        """Successful command should produce no output and clear failure state."""
        event = make_event(
            "Bash",
            command="npm run build",
            tool_result={"stdout": "Build succeeded", "stderr": "", "exit_code": 0},
        )
        result = run_hook("loop-detection.py", event)
        assert result.stdout.strip() == ""


class TestRepeatedFailures:
    def test_three_failures_triggers_recovery_advisory(self, run_hook, make_event, tmp_state_dir):
        """3 failures of the same command pattern should trigger recovery strategies."""
        event = make_event(
            "Bash",
            command="npm run build",
            tool_result={"stdout": "Build failed: module not found", "stderr": "", "exit_code": 1},
        )

        # Fire the same failing command 3 times
        run_hook("loop-detection.py", event)
        run_hook("loop-detection.py", event)
        result = run_hook("loop-detection.py", event)

        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "failed" in result.parsed["reason"].lower()
        assert "3" in result.parsed["reason"] or "retrying" in result.parsed["reason"].lower()


class TestBuildFailureClassification:
    def test_build_failure_mentions_dependencies(self, run_hook, make_event, tmp_state_dir):
        """Build failures should produce strategies mentioning dependencies."""
        event = make_event(
            "Bash",
            command="npm run build",
            tool_result={
                "stdout": "Error: Cannot find module 'lodash'",
                "stderr": "",
                "exit_code": 1,
            },
        )

        run_hook("loop-detection.py", event)
        run_hook("loop-detection.py", event)
        result = run_hook("loop-detection.py", event)

        assert result.parsed is not None
        reason = result.parsed["reason"].lower()
        assert "build" in reason or "dependencies" in reason or "module" in reason


class TestTestFailureClassification:
    def test_test_failure_mentions_assertion(self, run_hook, make_event, tmp_state_dir):
        """Test failures should produce strategies mentioning assertion diff."""
        event = make_event(
            "Bash",
            command="pytest tests/",
            tool_result={
                "stdout": "FAILED test_main.py::test_add - AssertionError: expected 4 but got 5",
                "stderr": "",
                "exit_code": 1,
            },
        )

        run_hook("loop-detection.py", event)
        run_hook("loop-detection.py", event)
        result = run_hook("loop-detection.py", event)

        assert result.parsed is not None
        reason = result.parsed["reason"].lower()
        assert "test" in reason or "assertion" in reason


class TestRealPostToolUseWireSchema:
    """F3 regression: real PostToolUse events deliver Bash results under
    `tool_response` (keys: stdout/stderr/interrupted/isImage/noOutputExpected
    — NO `tool_result`, NO exit_code). Before the fix, loop-detection.py read
    `event.get("tool_result", {})`, which is always empty on a real event, so
    the hook could never observe a failure and loop detection never fired.

    These events are built as raw dicts (not via `make_event`, whose
    `tool_result` kwarg only ever sets the WRONG `tool_result` key) to
    faithfully reproduce the real wire shape.
    """

    def test_three_real_tool_response_failures_triggers_recovery_advisory(
        self, run_hook, tmp_state_dir
    ):
        """3 repeats of a real `tool_response`-keyed Bash failure fire the advisory.

        This is the load-bearing regression test for F3: it asserts loop
        detection actually fires end-to-end via subprocess invocation of the
        real hook script, using the real PostToolUse wire shape.
        """
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm run build"},
            "tool_response": {
                "stdout": "Error: Cannot find module 'lodash'\nBuild failed",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
                # Deliberately NO exit_code — real Bash tool_response never has one.
            },
        }

        run_hook("loop-detection.py", event)
        run_hook("loop-detection.py", event)
        result = run_hook("loop-detection.py", event)

        assert result.returncode == 0, f"Hook crashed: stderr={result.stderr!r}"
        assert result.parsed is not None, (
            f"Expected a recovery advisory after 3 real tool_response failures, "
            f"got no JSON output: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.parsed["decision"] == "allow"
        reason = result.parsed["reason"].lower()
        assert "failed" in reason
        assert "build" in reason or "dependencies" in reason or "module" in reason

    def test_real_tool_response_success_produces_no_output(self, run_hook, tmp_state_dir):
        """A real `tool_response`-keyed successful Bash call stays silent."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm run build"},
            "tool_response": {
                "stdout": "Build succeeded",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("loop-detection.py", event)
        assert result.returncode == 0
        assert result.stdout.strip() == ""
