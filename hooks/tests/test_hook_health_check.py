"""Tests for hook-health-check.py hook."""

import importlib.util
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "hhc", str(HOOKS_DIR / "hook-health-check.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hhc():
    return load_module()


class TestCheckHook:
    def test_healthy_script_returns_none(self, hhc, tmp_path):
        script = tmp_path / "healthy.py"
        script.write_text(textwrap.dedent("""\
            import json, sys
            print(json.dumps({"decision": "allow", "reason": "ok"}))
            sys.exit(0)
        """))
        assert hhc.check_hook(script) is None

    def test_exit_code_gt_1_detected(self, hhc, tmp_path):
        script = tmp_path / "bad_exit.py"
        script.write_text(textwrap.dedent("""\
            import sys
            sys.exit(2)
        """))
        result = hhc.check_hook(script)
        assert result is not None
        assert "exit code 2" in result

    def test_traceback_in_stderr_detected(self, hhc, tmp_path):
        script = tmp_path / "raises.py"
        script.write_text(textwrap.dedent("""\
            raise RuntimeError("boom")
        """))
        result = hhc.check_hook(script)
        assert result is not None
        assert "stderr" in result
        assert "Traceback" in result or "RuntimeError" in result

    def test_exit_code_1_is_acceptable(self, hhc, tmp_path):
        """Exit code 1 is acceptable (hooks may exit 1 for non-error reasons)."""
        script = tmp_path / "exit1.py"
        script.write_text(textwrap.dedent("""\
            import sys
            sys.exit(1)
        """))
        assert hhc.check_hook(script) is None

    def test_syntax_error_detected(self, hhc, tmp_path):
        script = tmp_path / "syntax_err.py"
        script.write_text("def broken(\n")
        result = hhc.check_hook(script)
        assert result is not None
        assert "SyntaxError" in result or "exit code" in result


class TestCheckShHook:
    def test_valid_bash_returns_none(self, hhc, tmp_path):
        script = tmp_path / "good.sh"
        script.write_text(textwrap.dedent("""\
            #!/bin/bash
            echo "hello"
            exit 0
        """))
        assert hhc.check_sh_hook(script) is None

    def test_invalid_bash_detected(self, hhc, tmp_path):
        script = tmp_path / "bad.sh"
        script.write_text(textwrap.dedent("""\
            #!/bin/bash
            if then else fi while
            ((((
        """))
        result = hhc.check_sh_hook(script)
        assert result is not None
        assert "bash syntax error" in result


class TestGetExternalHookPaths:
    def test_extracts_external_paths(self, hhc, tmp_path):
        """External hook paths from settings.json are extracted."""
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "mcp__codesight-mcp__.*",
                        "hooks": [
                            {"type": "command", "command": "python3 ~/.config/codesight-mcp/pre-notify.py"}
                        ]
                    }
                ],
                "PostToolUse": [
                    {
                        "matcher": "mcp__codesight-mcp__.*",
                        "hooks": [
                            {"type": "command", "command": "python3 ~/.config/codesight-mcp/notify.py"}
                        ]
                    }
                ]
            }
        }
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings))
        # Override SETTINGS_PATH for test
        original = hhc.SETTINGS_PATH
        hhc.SETTINGS_PATH = settings_file
        try:
            paths = hhc.get_external_hook_paths()
            path_strs = [str(p) for p in paths]
            home = str(Path.home())
            assert f"{home}/.config/codesight-mcp/pre-notify.py" in path_strs
            assert f"{home}/.config/codesight-mcp/notify.py" in path_strs
        finally:
            hhc.SETTINGS_PATH = original

    def test_ignores_internal_hooks(self, hhc, tmp_path):
        """Paths inside ~/.claude/hooks/ are not returned (already checked)."""
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 ~/.claude/hooks/git-safety-guard.py"}
                        ]
                    }
                ]
            }
        }
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings))
        original = hhc.SETTINGS_PATH
        hhc.SETTINGS_PATH = settings_file
        try:
            paths = hhc.get_external_hook_paths()
            assert len(paths) == 0
        finally:
            hhc.SETTINGS_PATH = original

    def test_handles_missing_settings(self, hhc, tmp_path):
        """Missing settings.json returns empty list."""
        original = hhc.SETTINGS_PATH
        hhc.SETTINGS_PATH = tmp_path / "nonexistent.json"
        try:
            paths = hhc.get_external_hook_paths()
            assert paths == []
        finally:
            hhc.SETTINGS_PATH = original


class TestCheckExternalHook:
    def test_missing_file_returns_error(self, hhc, tmp_path):
        """Non-existent file returns 'file not found'."""
        result = hhc.check_external_hook(tmp_path / "nonexistent.py")
        assert result == "file not found"

    def test_existing_py_hook_checked(self, hhc, tmp_path):
        """Existing .py file is run through check_hook."""
        script = tmp_path / "ext_hook.py"
        script.write_text(textwrap.dedent("""\
            import json, sys
            print(json.dumps({"decision": "allow", "reason": "ok"}))
            sys.exit(0)
        """))
        assert hhc.check_external_hook(script) is None

    def test_existing_py_hook_unhealthy(self, hhc, tmp_path):
        """Unhealthy .py file returns error from check_hook."""
        script = tmp_path / "bad_ext.py"
        script.write_text("raise RuntimeError('boom')\n")
        result = hhc.check_external_hook(script)
        assert result is not None
        assert "Traceback" in result or "RuntimeError" in result or "exit code" in result

    def test_existing_sh_hook_checked(self, hhc, tmp_path):
        """Existing .sh file is run through check_sh_hook."""
        script = tmp_path / "ext_hook.sh"
        script.write_text(textwrap.dedent("""\
            #!/bin/bash
            echo "hello"
        """))
        assert hhc.check_external_hook(script) is None

    def test_existing_sh_hook_unhealthy(self, hhc, tmp_path):
        """Unhealthy .sh file returns error from check_sh_hook."""
        script = tmp_path / "bad_ext.sh"
        script.write_text("if then else fi while\n((((")
        result = hhc.check_external_hook(script)
        assert result is not None
        assert "bash syntax error" in result

    def test_unknown_extension_returns_none(self, hhc, tmp_path):
        """Unknown file extension returns None (skip silently)."""
        script = tmp_path / "hook.rb"
        script.write_text("puts 'hello'\n")
        assert hhc.check_external_hook(script) is None


class TestIntegration:
    def test_no_output_when_hooks_healthy(self, run_hook):
        """Full hook produces no output when all hooks are healthy."""
        result = run_hook("hook-health-check.py", {})
        # If all hooks in ~/.claude/hooks/ are healthy, output should be empty.
        # If some are unhealthy, we still verify valid JSON structure.
        if result.stdout.strip():
            parsed = json.loads(result.stdout)
            assert parsed["decision"] == "allow"
            assert "unhealthy" in parsed["reason"].lower()
        else:
            assert result.stdout.strip() == ""
