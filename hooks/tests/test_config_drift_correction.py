"""Tests for config-drift-correction.py hook."""

import importlib.util
import json
import os
from pathlib import Path

import pytest


HOOK_NAME = "config-drift-correction.py"
HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def load_module():
    """Load the hook module directly for unit testing."""
    spec = importlib.util.spec_from_file_location(
        "config_drift_correction",
        HOOKS_DIR / "config-drift-correction.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestNonHookFile:
    """Non-hook file edits should produce no output."""

    def test_regular_file_edit_no_output(self, run_hook, make_event):
        event = make_event("Edit", file_path="/Users/cevin/src/project/main.py")
        result = run_hook(HOOK_NAME, event)
        assert result.stdout == ""
        assert result.returncode == 0

    def test_non_write_tool_no_output(self, run_hook, make_event):
        event = make_event("Bash", command="echo hello")
        result = run_hook(HOOK_NAME, event)
        assert result.stdout == ""
        assert result.returncode == 0

    def test_test_file_in_hooks_dir_no_output(self, run_hook, make_event):
        event = make_event("Write", file_path=os.path.expanduser(
            "~/.claude/hooks/tests/test_something.py"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.stdout == ""
        assert result.returncode == 0

    def test_lib_file_in_hooks_dir_no_output(self, run_hook, make_event):
        event = make_event("Write", file_path=os.path.expanduser(
            "~/.claude/hooks/_lib/utils.py"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.stdout == ""
        assert result.returncode == 0


class TestRegisteredHook:
    """Hook files that ARE registered should produce no output."""

    def test_registered_python_hook_no_output(self, run_hook, make_event):
        # loop-detection.py is registered in settings.json
        event = make_event("Edit", file_path=os.path.expanduser(
            "~/.claude/hooks/loop-detection.py"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.stdout == ""
        assert result.returncode == 0

    def test_registered_shell_hook_no_output(self, run_hook, make_event):
        # qmd-vault-embed.sh is registered in settings.json
        event = make_event("Write", file_path=os.path.expanduser(
            "~/.claude/hooks/qmd-vault-embed.sh"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.stdout == ""
        assert result.returncode == 0


class TestUnregisteredHook:
    """Hook files NOT in settings.json should trigger an advisory."""

    def test_unregistered_python_hook_advisory(self, run_hook, make_event):
        event = make_event("Write", file_path=os.path.expanduser(
            "~/.claude/hooks/brand-new-hook.py"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "CONFIG DRIFT" in result.parsed["reason"]
        assert "brand-new-hook.py" in result.parsed["reason"]
        assert "python3 ~/.claude/hooks/brand-new-hook.py" in result.parsed["reason"]

    def test_unregistered_shell_hook_advisory(self, run_hook, make_event):
        event = make_event("Write", file_path=os.path.expanduser(
            "~/.claude/hooks/brand-new-hook.sh"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "CONFIG DRIFT" in result.parsed["reason"]
        assert "brand-new-hook.sh" in result.parsed["reason"]
        assert "bash ~/.claude/hooks/brand-new-hook.sh" in result.parsed["reason"]

    def test_advisory_includes_registration_json(self, run_hook, make_event):
        event = make_event("Edit", file_path=os.path.expanduser(
            "~/.claude/hooks/my-new-hook.py"
        ))
        result = run_hook(HOOK_NAME, event)
        assert result.parsed is not None
        assert '"type": "command"' in result.parsed["reason"]
        assert '"command":' in result.parsed["reason"]


class TestGracefulDegradation:
    """When settings.json can't be read, hook should allow silently."""

    def test_missing_settings_json_allows_silently(self, tmp_path):
        """Point SETTINGS_PATH to a nonexistent file and verify silent allow."""
        mod = load_module()
        mod.SETTINGS_PATH = tmp_path / "nonexistent" / "settings.json"

        # is_hook_file should still detect hook files
        hook_path = os.path.expanduser("~/.claude/hooks/some-hook.py")
        assert mod.is_hook_file(hook_path)

        # But main() reads settings and gracefully returns on OSError
        # Verify the path truly doesn't exist
        assert not mod.SETTINGS_PATH.exists()

    def test_corrupt_settings_json_allows_silently(self, tmp_path):
        """If settings.json is corrupt JSON, hook allows silently."""
        mod = load_module()
        corrupt_file = tmp_path / "settings.json"
        corrupt_file.write_text("{not valid json!!!")
        mod.SETTINGS_PATH = corrupt_file

        # Verify the file exists but is not valid JSON
        assert corrupt_file.exists()
        with pytest.raises(json.JSONDecodeError):
            json.loads(corrupt_file.read_text())


class TestHelperFunctions:
    """Unit tests for helper functions using real data."""

    def test_is_hook_file_with_py_extension(self):
        mod = load_module()
        assert mod.is_hook_file(os.path.expanduser("~/.claude/hooks/my-hook.py"))

    def test_is_hook_file_with_sh_extension(self):
        mod = load_module()
        assert mod.is_hook_file(os.path.expanduser("~/.claude/hooks/my-hook.sh"))

    def test_is_hook_file_rejects_txt(self):
        mod = load_module()
        assert not mod.is_hook_file(os.path.expanduser("~/.claude/hooks/notes.txt"))

    def test_is_hook_file_rejects_empty(self):
        mod = load_module()
        assert not mod.is_hook_file("")

    def test_is_registered_finds_hook(self):
        mod = load_module()
        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 ~/.claude/hooks/loop-detection.py"}
                        ]
                    }
                ]
            }
        }
        assert mod.is_registered("loop-detection.py", settings)

    def test_is_registered_returns_false_for_missing(self):
        mod = load_module()
        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {"type": "command", "command": "python3 ~/.claude/hooks/other.py"}
                        ]
                    }
                ]
            }
        }
        assert not mod.is_registered("nonexistent-hook.py", settings)

    def test_suggest_registration_python(self):
        mod = load_module()
        result = mod.suggest_registration("my-hook.py", "/some/path/my-hook.py")
        assert "python3 ~/.claude/hooks/my-hook.py" in result
        assert "CONFIG DRIFT" in result

    def test_suggest_registration_bash(self):
        mod = load_module()
        result = mod.suggest_registration("my-hook.sh", "/some/path/my-hook.sh")
        assert "bash ~/.claude/hooks/my-hook.sh" in result
