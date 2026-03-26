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


class TestPlaceholderDetection:
    def test_todo_in_output_triggers_correction(self, run_hook, make_event):
        """Agent output with TODO should trigger placeholder correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the login feature.",
                tool_result="Added the login form. TODO: finish this validation logic.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "TODO" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_fixme_in_output_triggers_correction(self, run_hook, make_event):
        """Agent output with FIXME should trigger placeholder correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the login feature.",
                tool_result="Added the login form. FIXME: broken edge case here.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "FIXME" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_hack_in_output_triggers_correction(self, run_hook, make_event):
        """Agent output with HACK should trigger placeholder correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the login feature.",
                tool_result="Added the login form. HACK: temporary workaround for auth.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "HACK" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_placeholder_in_output_triggers_correction(self, run_hook, make_event):
        """Agent output with 'placeholder' should trigger correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the login feature.",
                tool_result="Added a placeholder text for the error message.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "placeholder" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_clean_output_no_correction(self, run_hook, make_event):
        """Agent output with no markers should produce no output."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the login feature.",
                tool_result="Successfully implemented the login feature with full validation.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.stdout.strip() == ""
        finally:
            _deactivate_session()

    def test_placeholder_fires_without_task_count(self, run_hook, make_event):
        """Placeholder detection fires even when prompt has no task count."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Please review this code.",
                tool_result="Reviewed the code. TODO: check edge cases still.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "TODO" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_placeholder_includes_rationalization(self, run_hook, make_event):
        """Placeholder correction must include the named rationalization."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Implement the login feature.",
                tool_result="Done. TODO: add error handling later.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "follow-up" in result.parsed["reason"]
        finally:
            _deactivate_session()


class TestIncompleteRefactorDetection:
    def test_deprecated_marker_triggers_correction(self, run_hook, make_event):
        """Agent output with DEPRECATED marker should trigger refactor correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Refactor the auth module.",
                tool_result="Added new auth handler. DEPRECATED: old auth handler still in place.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "deprecated" in result.parsed["reason"].lower()
            assert "Case study #25" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_old_comment_triggers_correction(self, run_hook, make_event):
        """Agent output with '# old:' comment should trigger refactor correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Update the config parser.",
                tool_result="New parser implemented.\n# old: previous parser used regex",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "Case study #25" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_clean_output_no_refactor_warning(self, run_hook, make_event):
        """Agent output without deprecated markers should not trigger refactor correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Refactor the auth module.",
                tool_result="Replaced the old auth handler with the new implementation. All tests pass.",
            )
            result = run_hook("deliverable-correction.py", event)
            # Should not have any correction (no placeholders, no deprecated markers, no count mismatch)
            assert result.stdout.strip() == ""
        finally:
            _deactivate_session()

    def test_at_deprecated_annotation_triggers_correction(self, run_hook, make_event):
        """Agent output with @deprecated annotation should trigger refactor correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Update the API endpoints.",
                tool_result="Added new v2 endpoints. Left @deprecated on old v1 endpoints.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
            assert "Case study #25" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_refactor_includes_rationalization(self, run_hook, make_event):
        """Refactor correction must include the named rationalization."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Refactor the auth module.",
                tool_result="New auth handler added. DEPRECATED old handler kept for reference.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "left the old code as a reference" in result.parsed["reason"]
        finally:
            _deactivate_session()

    def test_legacy_coexistence_triggers_correction(self, run_hook, make_event):
        """Agent output with old_xxx and new_xxx coexisting should trigger correction."""
        _activate_session()
        try:
            event = make_event(
                "Agent",
                prompt="Rename the handler functions.",
                tool_result="Renamed: old_handler still exists alongside new_handler.",
            )
            result = run_hook("deliverable-correction.py", event)
            assert result.parsed is not None
            assert "CORRECTION" in result.parsed["reason"]
        finally:
            _deactivate_session()
