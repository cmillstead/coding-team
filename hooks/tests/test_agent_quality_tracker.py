"""Tests for agent-quality-tracker.py hook."""


class TestNonSkillTool:
    def test_non_skill_tool_produces_no_output(self, run_hook, make_event):
        """Non-Skill tool_name should be silently ignored."""
        event = make_event("Bash", command="ls -la")
        result = run_hook("agent-quality-tracker.py", event)
        assert result.stdout.strip() == ""
        assert result.returncode == 0

    def test_read_tool_produces_no_output(self, run_hook, make_event):
        """Read tool should be silently ignored."""
        event = make_event("Read", file_path="/some/file.py")
        result = run_hook("agent-quality-tracker.py", event)
        assert result.stdout.strip() == ""


class TestSkillWithNormalOutput:
    def test_skill_with_normal_output_is_silent(self, run_hook, make_event):
        """Skill with successful output should log but produce no stdout advisory."""
        event = make_event(
            "Skill",
            skill="coding-team",
            tool_result={"stdout": "Feature implemented successfully", "exit_code": 0},
        )
        result = run_hook("agent-quality-tracker.py", event)
        # Should be silent — no advisory for successful skill runs
        assert result.parsed is None or "reason" not in (result.parsed or {})
        assert result.returncode == 0


class TestSkillWithError:
    def test_skill_with_nonzero_exit_code_triggers_advisory(self, run_hook, make_event):
        """Skill with exit_code != 0 should produce a quality gate advisory."""
        event = make_event(
            "Skill",
            skill="scan-code",
            tool_result={"stdout": "Something went wrong", "exit_code": 1},
        )
        result = run_hook("agent-quality-tracker.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "QUALITY GATE" in result.parsed["reason"]
        assert "scan-code" in result.parsed["reason"]

    def test_skill_with_exit_code_zero_and_error_keyword_not_flagged(self, run_hook, make_event):
        """Skill with exit_code 0 should trust the exit code, even if output contains 'error'."""
        event = make_event(
            "Skill",
            skill="scan-security",
            tool_result={"stdout": "Found 0 errors in security scan", "exit_code": 0},
        )
        result = run_hook("agent-quality-tracker.py", event)
        # exit_code 0 means success — should NOT flag as error
        assert result.parsed is None or "QUALITY GATE" not in (result.parsed or {}).get("reason", "")


class TestSkillWithEmptyOutput:
    def test_skill_with_empty_output_triggers_silent_failure_advisory(self, run_hook, make_event):
        """Skill with no output should trigger a silent failure advisory."""
        event = make_event(
            "Skill",
            skill="debug",
            tool_result={"stdout": "", "exit_code": 0},
        )
        result = run_hook("agent-quality-tracker.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "silent failure" in result.parsed["reason"].lower() or "no output" in result.parsed["reason"].lower()
        assert "debug" in result.parsed["reason"]

    def test_skill_with_whitespace_only_output_triggers_advisory(self, run_hook, make_event):
        """Skill with whitespace-only output should be treated as empty."""
        event = make_event(
            "Skill",
            skill="review",
            tool_result={"stdout": "   \n  ", "exit_code": 0},
        )
        result = run_hook("agent-quality-tracker.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "no output" in result.parsed["reason"].lower() or "silent failure" in result.parsed["reason"].lower()


class TestStructureNotBehaviorDetection:
    """Case study #22: detect tests that read source files as text instead of calling functions."""

    def test_open_read_triggers_warning(self, run_hook, make_event):
        """Output containing open('module.py').read() should trigger structure-not-behavior advisory."""
        event = make_event(
            "Skill",
            skill="coding-team",
            tool_result={
                "stdout": 'content = open("module.py", "r").read()\nassert "def main" in content',
                "exit_code": 0,
            },
        )
        result = run_hook("agent-quality-tracker.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "structure-not-behavior" in result.parsed["reason"].lower()
        assert "Case study #22" in result.parsed["reason"]

    def test_path_read_text_triggers_warning(self, run_hook, make_event):
        """Output containing Path('src/foo.py').read_text() should trigger advisory."""
        event = make_event(
            "Skill",
            skill="coding-team",
            tool_result={
                "stdout": 'source = Path("src/foo.py").read_text()\nassert "class Foo" in source',
                "exit_code": 0,
            },
        )
        result = run_hook("agent-quality-tracker.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "structure-not-behavior" in result.parsed["reason"].lower()

    def test_normal_behavioral_assert_no_warning(self, run_hook, make_event):
        """Output with normal assert result == expected should NOT trigger the warning."""
        event = make_event(
            "Skill",
            skill="coding-team",
            tool_result={
                "stdout": "result = add(2, 3)\nassert result == 5\nAll tests passed.",
                "exit_code": 0,
            },
        )
        result = run_hook("agent-quality-tracker.py", event)
        # Should be silent — no advisory for behavioral tests
        assert result.parsed is None or "structure-not-behavior" not in (result.parsed or {}).get("reason", "").lower()

    def test_assert_string_in_content_triggers_warning(self, run_hook, make_event):
        """Output containing assert 'def main' in content should trigger advisory."""
        event = make_event(
            "Skill",
            skill="coding-team",
            tool_result={
                "stdout": 'content = read_file("app.py")\nassert "def main" in content',
                "exit_code": 0,
            },
        )
        result = run_hook("agent-quality-tracker.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "structure-not-behavior" in result.parsed["reason"].lower()
