"""Tests for codesight-hooks.py hook."""


class TestPreToolUseAgent:
    def test_injects_codesight_instruction_into_agent_prompt(self, run_hook, make_event):
        event = make_event("Agent", prompt="Search for the function definition")
        result = run_hook("codesight-hooks.py", event)
        assert result.parsed is not None
        # Should have hookSpecificOutput with updatedInput
        hook_output = result.parsed.get("hookSpecificOutput", {})
        updated = hook_output.get("updatedInput", {})
        assert "codesight" in updated.get("prompt", "").lower()
        assert "search_text" in updated.get("prompt", "")


class TestPostToolUseWrite:
    def test_no_output_for_non_src_path(self, run_hook, make_event):
        event = make_event(
            "Write",
            file_path="/tmp/some-file.txt",
            content="hello",
            tool_result="File written",
        )
        result = run_hook("codesight-hooks.py", event)
        # PostToolUse Write to non-~/src/ path should produce no output
        assert result.stdout.strip() == ""


class TestNonAgentTool:
    def test_no_output_for_bash(self, run_hook, make_event):
        event = make_event("Bash", command="ls -la")
        result = run_hook("codesight-hooks.py", event)
        assert result.stdout.strip() == ""

    def test_no_output_for_read(self, run_hook, make_event):
        event = make_event("Read", file_path="/tmp/file.py")
        result = run_hook("codesight-hooks.py", event)
        assert result.stdout.strip() == ""
