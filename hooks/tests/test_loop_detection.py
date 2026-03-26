"""Tests for loop-detection.py hook."""


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
