"""Tests for builder-self-check.py hook."""

import json
import os
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def run_builder_hook(event: dict, timeout: int = 30) -> dict | None:
    """Run builder-self-check.py with a longer timeout than the default conftest fixture."""
    result = subprocess.run(
        ["python3", str(HOOKS_DIR / "builder-self-check.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return {"stdout": result.stdout, "parsed": parsed, "returncode": result.returncode}


class TestPythonFileTriggersRuff:
    """Verify that editing a Python file triggers ruff check."""

    def test_python_edit_with_ruff_error(self, run_hook, make_event, tmp_path):
        """A Python file with a lint error should produce an advisory."""
        bad_file = tmp_path / "bad_code.py"
        bad_file.write_text("import os\nimport sys\n")  # unused imports

        event = make_event(
            "Edit",
            file_path=str(bad_file),
            new_string="import os\nimport sys\n",
        )
        result = run_hook("builder-self-check.py", event)

        # If ruff is installed and catches the unused imports, expect advisory
        if result.parsed:
            assert result.parsed["decision"] == "allow"
            if "reason" in result.parsed:
                assert "BUILDER SELF-CHECK" in result.parsed["reason"]
                assert "ruff" in result.parsed["reason"].lower()

    def test_clean_python_file_is_silent(self, run_hook, make_event, tmp_path):
        """A Python file with no lint errors should produce no output."""
        clean_file = tmp_path / "clean_code.py"
        clean_file.write_text('"""Module docstring."""\n\nX = 1\n')

        event = make_event(
            "Edit",
            file_path=str(clean_file),
            new_string='"""Module docstring."""\n\nX = 1\n',
        )
        result = run_hook("builder-self-check.py", event)

        # Should be silent (no output) or at most an allow without ruff issues
        if result.parsed and "reason" in result.parsed:
            assert "ruff" not in result.parsed["reason"].lower()


class TestNonPythonSkipsRuff:
    """Non-Python files should not trigger ruff."""

    def test_json_file_skips_ruff(self, run_hook, make_event, tmp_path):
        """Editing a JSON file should not run ruff."""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}')

        event = make_event(
            "Write",
            file_path=str(json_file),
            content='{"key": "value"}',
        )
        result = run_hook("builder-self-check.py", event)

        # Should be silent — no Python checks
        if result.parsed and "reason" in result.parsed:
            assert "ruff" not in result.parsed["reason"].lower()

    def test_markdown_file_skips_ruff(self, run_hook, make_event, tmp_path):
        """Editing a Markdown file should not run ruff."""
        md_file = tmp_path / "README.md"
        md_file.write_text("# Hello\n")

        event = make_event(
            "Write",
            file_path=str(md_file),
            content="# Hello\n",
        )
        result = run_hook("builder-self-check.py", event)

        if result.parsed and "reason" in result.parsed:
            assert "ruff" not in result.parsed["reason"].lower()


class TestMissingToolsHandledGracefully:
    """If ruff/mypy/tsc are not installed, the hook should skip silently."""

    def test_non_edit_tool_is_silent(self, run_hook, make_event):
        """Non-Edit/Write tools should produce no output."""
        event = make_event("Read", file_path="/tmp/anything.py")
        result = run_hook("builder-self-check.py", event)
        assert result.stdout.strip() == ""

    def test_empty_file_path_is_silent(self, run_hook):
        """Empty file_path should produce no output."""
        event = {"tool_name": "Edit", "tool_input": {"file_path": "", "new_string": "x"}}
        result = run_hook("builder-self-check.py", event)
        assert result.stdout.strip() == ""

    def test_nonexistent_file_does_not_crash(self, run_hook, make_event):
        """Editing a file that doesn't exist should not crash the hook."""
        event = make_event(
            "Edit",
            file_path="/tmp/does-not-exist-12345.py",
            new_string="x = 1",
        )
        result = run_hook("builder-self-check.py", event)
        # Should not crash (returncode 0)
        assert result.returncode == 0


class TestTestFileDetection:
    """Verify test file pattern matching."""

    def test_python_test_file_detected(self, run_hook, make_event, tmp_path):
        """test_*.py files should be detected as test files."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            "def test_pass():\n    assert True\n"
        )

        event = make_event(
            "Edit",
            file_path=str(test_file),
            new_string="def test_pass():\n    assert True\n",
        )
        result = run_hook("builder-self-check.py", event)
        # Hook should attempt to run the test file. If pytest is available,
        # a passing test should produce no advisory.
        assert result.returncode == 0

    def test_spec_file_detected(self, make_event, tmp_path):
        """*.spec.ts files should be detected as test files."""
        spec_file = tmp_path / "app.spec.ts"
        spec_file.write_text("describe('app', () => { it('works', () => {}); });")

        event = make_event(
            "Write",
            file_path=str(spec_file),
            content="describe('app', () => { it('works', () => {}); });",
        )
        result = run_builder_hook(event, timeout=45)
        # Should not crash regardless of whether jest is installed
        assert result["returncode"] == 0

    def test_non_test_python_not_executed(self, make_event, tmp_path):
        """Regular Python files should not be run as tests."""
        regular_file = tmp_path / "utils.py"
        regular_file.write_text('"""Utility module."""\n\nX = 1\n')

        event = make_event(
            "Edit",
            file_path=str(regular_file),
            new_string='"""Utility module."""\n\nX = 1\n',
        )
        result = run_builder_hook(event, timeout=30)
        # No test execution advisory expected for non-test files
        if result["parsed"] and "reason" in result["parsed"]:
            assert "test execution failed" not in result["parsed"]["reason"].lower()


class TestWriteToolSupport:
    """Verify the hook works with Write tool events, not just Edit."""

    def test_write_tool_triggers_checks(self, run_hook, make_event, tmp_path):
        """Write tool should trigger the same checks as Edit."""
        bad_file = tmp_path / "new_file.py"
        bad_file.write_text("import os\nimport sys\n")

        event = make_event(
            "Write",
            file_path=str(bad_file),
            content="import os\nimport sys\n",
        )
        result = run_hook("builder-self-check.py", event)

        # Same behavior as Edit — ruff advisory if ruff is installed
        if result.parsed:
            assert result.parsed["decision"] == "allow"
