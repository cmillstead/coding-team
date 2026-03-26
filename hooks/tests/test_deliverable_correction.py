"""Tests for deliverable-correction.py hook."""
import json
import time
from pathlib import Path


SESSION_FILE = Path("/tmp/coding-team-session.json")


def _activate_session():
    """Create a fresh session file so the hook fires."""
    SESSION_FILE.write_text(json.dumps({"ts": time.time(), "phase": "execution"}))


def _deactivate_session():
    """Remove session file."""
    SESSION_FILE.unlink(missing_ok=True)


class TestNonAgentTool:
    def test_non_agent_tool_no_output(self, run_hook, make_event):
        event = make_event("Bash", command="ls")
        result = run_hook("deliverable-correction.py", event)
        assert result.stdout.strip() == ""


class TestNoSession:
    def test_no_session_file_no_output(self, run_hook, make_event):
        _deactivate_session()
        event = make_event(
            "Agent",
            prompt="Complete 5 tasks",
            tool_result="I completed 3 tasks",
        )
        result = run_hook("deliverable-correction.py", event)
        assert result.stdout.strip() == ""


class TestCompletionDetection:
    def test_incomplete_delivery_emits_correction(self, run_hook, make_event):
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="You have 5 tasks to complete.",
                tool_result="I have completed 3 of the tasks successfully.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "3" in result.parsed["reason"]
            assert "5" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_complete_delivery_no_output(self, run_hook, make_event):
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="You have 5 tasks to complete.",
                tool_result="I have completed all 5 tasks successfully.",
            )
            result = run_hook("deliverable-correction.py", event)
            # completed == expected, no correction needed
            assert result.parsed is None or "CORRECTION" not in (result.parsed or {}).get("reason", "")
        finally:
            _deactivate_session()

    def test_no_count_in_prompt_no_output(self, run_hook, make_event):
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Please review this code.",
                tool_result="I have completed the review.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.stdout.strip() == ""
        finally:
            _deactivate_session()


class TestExtractExpectedCount:
    def test_n_tasks_pattern(self, run_hook, make_event):
        """'8 tasks' in prompt should extract 8."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="You have 8 tasks to implement.",
                tool_result="I completed 4 items.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "4" in result.parsed["reason"]
            assert "8" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_task_n_of_m_pattern(self, run_hook, make_event):
        """'Task 1 of 6' in prompt should extract 6."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Task 1 of 6: implement the login flow.",
                tool_result="I completed 2 tasks.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_numbered_list_extraction(self, run_hook, make_event):
        """Numbered list items should be counted."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the following:\n1. Add login\n2. Add logout\n3. Add profile\n4. Add settings",
                tool_result="I completed 2 of these items.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_single_task_no_output(self, run_hook, make_event):
        """A single task (expected < 2) should not trigger the hook."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="You have 1 task to complete.",
                tool_result="I completed 0 items.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.stdout.strip() == ""
        finally:
            _deactivate_session()


class TestNamedRationalization:
    def test_correction_includes_rationalization(self, run_hook, make_event):
        """Correction message must include the named rationalization."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="You have 5 tasks to complete.",
                tool_result="I have completed 3 of the tasks.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "pattern is established" in result.parsed["reason"]
        finally:
            _deactivate_session()


class TestNoCompletionClaim:
    def test_no_completion_count_in_output_no_correction(self, run_hook, make_event):
        """If the output doesn't claim a specific count, no correction is emitted."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="You have 5 tasks to complete.",
                tool_result="I have made progress on the tasks.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.stdout.strip() == ""
        finally:
            _deactivate_session()
