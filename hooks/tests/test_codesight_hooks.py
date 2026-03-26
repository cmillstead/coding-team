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


class TestStyleInjection:
    def test_code_work_prompt_gets_style_injection(self, run_hook, make_event):
        """Agent prompt with code work signals gets style instruction appended."""
        event = make_event("Agent", prompt="Implement the login feature")
        result = run_hook("codesight-hooks.py", event)
        assert result.parsed is not None
        output = result.parsed.get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {}).get("prompt", "")
        assert "code-style.md" in updated
        assert "golden-principles.md" in updated

    def test_non_code_prompt_no_style_injection(self, run_hook, make_event):
        """Agent prompt without code signals does not get style injection."""
        event = make_event("Agent", prompt="Summarize the meeting notes")
        result = run_hook("codesight-hooks.py", event)
        assert result.parsed is not None
        output = result.parsed.get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {}).get("prompt", "")
        assert "MANDATORY SEARCH RULES" in updated  # codesight still injected
        assert "code-style.md" not in updated

    def test_design_prompt_gets_style_injection(self, run_hook, make_event):
        """Agent prompt with design/architecture signals gets style injection."""
        event = make_event("Agent", prompt="Design the database schema architecture")
        result = run_hook("codesight-hooks.py", event)
        assert result.parsed is not None
        output = result.parsed.get("hookSpecificOutput", {})
        updated = output.get("updatedInput", {}).get("prompt", "")
        assert "golden-principles.md" in updated


class TestNonAgentTool:
    def test_no_output_for_bash(self, run_hook, make_event):
        event = make_event("Bash", command="ls -la")
        result = run_hook("codesight-hooks.py", event)
        assert result.stdout.strip() == ""

    def test_no_output_for_read(self, run_hook, make_event):
        event = make_event("Read", file_path="/tmp/file.py")
        result = run_hook("codesight-hooks.py", event)
        assert result.stdout.strip() == ""
