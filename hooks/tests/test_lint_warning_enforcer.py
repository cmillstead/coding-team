"""Tests for lint-warning-enforcer.py hook."""

import json


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
            "tool_output": "total 42\ndrwxr-xr-x  5 user  staff  160 Mar 26 file.txt",
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""

    def test_git_command_produces_no_output(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_output": "On branch main\nnothing to commit",
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""


class TestLintWithWarnings:
    def test_npm_run_lint_with_warnings_triggers_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm run lint"},
            "tool_output": (
                "src/app.ts(12,5): warning: unused variable 'x'\n"
                "src/utils.ts(8,3): warning: missing return type\n"
            ),
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
            "tool_output": "src/index.ts(5,1): warning: implicit any type\n",
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "warning" in result.parsed["reason"].lower()

    def test_cargo_clippy_with_warnings_triggers_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "cargo clippy"},
            "tool_output": "warning: unused import `std::io`\n",
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"


class TestLintCleanOutput:
    def test_eslint_clean_output_no_advisory(self, run_hook):
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "eslint src/"},
            "tool_output": "All files pass linting.\n",
        }
        result = run_hook("lint-warning-enforcer.py", event)
        assert result.stdout.strip() == ""


class TestExcludedWarningPatterns:
    def test_npm_warn_is_excluded(self, run_hook):
        """npm warn lines should be filtered out as false positives."""
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "npm run build"},
            "tool_output": "npm warn deprecated glob@7.2.0\nnpm warn deprecated inflight@1.0.6\nBuild complete.\n",
        }
        result = run_hook("lint-warning-enforcer.py", event)
        # npm warn lines are excluded — should produce no advisory
        assert result.stdout.strip() == ""
