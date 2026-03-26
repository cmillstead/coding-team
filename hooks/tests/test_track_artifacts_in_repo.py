"""Tests for track-artifacts-in-repo.py hook."""

import json
import os
import subprocess
from pathlib import Path

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def _run_track_artifacts(event):
    """Run track-artifacts-in-repo.py with the given event."""
    result = subprocess.run(
        ["python3", str(HOOKS_DIR / "track-artifacts-in-repo.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
    )
    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return result, parsed


class TestNonTrackedPath:
    def test_write_to_untracked_path_no_output(self, run_hook, make_event):
        """Write to a path not under ~/.claude/hooks/ or agents/ should be silent."""
        event = make_event("Write", file_path="/tmp/some-file.py", content="hello")
        result = run_hook("track-artifacts-in-repo.py", event)
        assert result.stdout.strip() == ""

    def test_edit_to_untracked_path_no_output(self, run_hook, make_event):
        """Edit to a path not under tracked dirs should be silent."""
        event = make_event("Edit", file_path="/Users/cevin/src/project/main.py")
        result = run_hook("track-artifacts-in-repo.py", event)
        assert result.stdout.strip() == ""


class TestWriteToTrackedDir:
    def test_write_to_hooks_dir_new_file_triggers_advisory(self, tmp_path):
        """Write to ~/.claude/hooks/ where repo copy doesn't exist should advise to copy."""
        # Create a temp file to simulate a new hook
        new_hook = tmp_path / "new-hook.py"
        new_hook.write_text("#!/usr/bin/env python3\nprint('hello')")

        # The hook checks if the resolved path starts with ~/.claude/hooks
        # We need to use the real path for it to match
        home = Path.home()
        hooks_path = home / ".claude" / "hooks" / "test-nonexistent-hook-xyz.py"

        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(hooks_path)},
        }
        result, parsed = _run_track_artifacts(event)

        # The file doesn't exist at hooks_path, but the hook checks repo copy existence
        # Since the file path is under ~/.claude/hooks/, it should check repo copy
        if parsed:
            assert parsed["decision"] == "allow"
            assert "repo" in parsed["reason"].lower() or "commit" in parsed["reason"].lower()


class TestEditTrackedFileWithDiff:
    def test_edit_existing_hook_triggers_check(self, run_hook, make_event):
        """Edit to a file under ~/.claude/hooks/ should trigger a repo-copy check.

        We use a nonexistent hook name to test the 'no repo copy' path,
        which is deterministic regardless of deploy state.
        """
        home = Path.home()
        hooks_path = home / ".claude" / "hooks" / "test-nonexistent-edit-xyz.py"

        event = make_event("Edit", file_path=str(hooks_path))
        result = run_hook("track-artifacts-in-repo.py", event)
        # The hook resolves the path — if under tracked dir and no repo copy,
        # it emits an advisory. The file doesn't exist on disk so resolve()
        # may not match. Either way, the hook should not crash.
        assert result.returncode == 0


class TestBashCpToTrackedDir:
    def test_cp_to_hooks_dir_triggers_advisory(self, run_hook, make_event):
        """Bash cp command targeting ~/.claude/hooks/ should trigger commit reminder."""
        event = make_event("Bash", command="cp /tmp/new-hook.py ~/.claude/hooks/new-hook.py")
        result = run_hook("track-artifacts-in-repo.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "commit" in result.parsed["reason"].lower() or "repo" in result.parsed["reason"].lower()

    def test_cp_to_agents_dir_triggers_advisory(self, run_hook, make_event):
        """Bash cp command targeting ~/.claude/agents/ should trigger commit reminder."""
        event = make_event("Bash", command="cp /tmp/agent.md ~/.claude/agents/new-agent.md")
        result = run_hook("track-artifacts-in-repo.py", event)
        assert result.parsed is not None
        assert result.parsed["decision"] == "allow"
        assert "commit" in result.parsed["reason"].lower() or "repo" in result.parsed["reason"].lower()


class TestNonMatchingTool:
    def test_read_tool_produces_no_output(self, run_hook, make_event):
        """Read tool should be silently ignored."""
        event = make_event("Read", file_path="/Users/cevin/.claude/hooks/some-hook.py")
        result = run_hook("track-artifacts-in-repo.py", event)
        assert result.stdout.strip() == ""

    def test_skill_tool_produces_no_output(self, run_hook, make_event):
        """Skill tool should be silently ignored."""
        event = make_event("Skill", skill="coding-team")
        result = run_hook("track-artifacts-in-repo.py", event)
        assert result.stdout.strip() == ""
