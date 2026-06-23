"""Tests for lint-warning-enforcer.py hook."""


class TestNonBashTool:
    def test_non_bash_tool_produces_no_output(self, run_hook, make_event):
        event = make_event("Edit", file_path="/src/main.py")
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""


class TestNonLintCommand:
    def test_ls_command_produces_no_output(self, run_hook):
        """Non-lint Bash command should be silently ignored."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "tool_response": {
                "stdout": "total 42\ndrwxr-xr-x  5 user  staff  160 Mar 26 file.txt",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""

    def test_git_command_produces_no_output(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_response": {
                "stdout": "On branch main\nnothing to commit",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""


class TestLintWithWarnings:
    def test_npm_run_lint_with_warnings_triggers_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm run lint"},
            "tool_response": {
                "stdout": (
                    "src/app.ts(12,5): warning: unused variable 'x'\n"
                    "src/utils.ts(8,3): warning: missing return type\n"
                ),
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "warning" in result.parsed["reason"].lower()
        assert "2" in result.parsed["reason"]  # 2 warnings

    def test_tsc_with_warnings_triggers_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "tsc --noEmit"},
            "tool_response": {
                "stdout": "src/index.ts(5,1): warning: implicit any type\n",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "warning" in result.parsed["reason"].lower()

    def test_cargo_clippy_with_warnings_triggers_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "cargo clippy"},
            "tool_response": {
                "stdout": "warning: unused import `std::io`\n",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"


class TestLintCleanOutput:
    def test_eslint_clean_output_no_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "eslint src/"},
            "tool_response": {
                "stdout": "All files pass linting.\n",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""


class TestExcludedWarningPatterns:
    def test_npm_warn_is_excluded(self, run_hook):
        """npm warn lines should be filtered out as false positives."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm run build"},
            "tool_response": {
                "stdout": "npm warn deprecated glob@7.2.0\nnpm warn deprecated inflight@1.0.6\nBuild complete.\n",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        # npm warn lines are excluded — should produce no advisory
        assert result.stdout.strip() == ""


class TestToolResultRouting:
    def test_lint_warnings_in_tool_response_trigger_advisory(self, run_hook):
        """Real PostToolUse Bash event shape: tool_response dict (no exit_code) with stdout containing lint warnings."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "ruff check src/"},
            "tool_response": {
                "stdout": (
                    "src/foo.py:10:5: warning: invalid escape sequence '\\d'\n"
                    "src/bar.py:22:1: warning: trailing whitespace\n"
                ),
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.parsed is not None, "Advisory must fire for lint warnings in tool_response"
        assert result.parsed["decision"] == "allow"
        reason = result.parsed["reason"]
        assert "warning" in reason.lower()
        assert "2" in reason  # both warning lines counted

    def test_empty_tool_response_returns_silently(self, run_hook):
        """Empty / absent tool_response must not raise and must produce no output (fail-open)."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "mypy src/"},
            # tool_response is absent — hook must return silently
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""

    def test_blank_stdout_tool_response_returns_silently(self, run_hook):
        """tool_response with empty stdout must produce no output (fail-open early-out)."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "pylint src/"},
            "tool_response": {
                "stdout": "",
                "stderr": "",
                "interrupted": False,
                "isImage": False,
                "noOutputExpected": False,
            },
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""
