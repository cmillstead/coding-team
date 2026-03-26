"""Tests for reread-before-edit.py hook."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


class TestSessionIsolation:
    def test_different_session_ids_produce_different_state_files(self):
        """Verify that different CLAUDE_SESSION_ID values yield different state file paths."""
        session_a = "test-session-aaa"
        session_b = "test-session-bbb"

        hash_a = hashlib.sha256(session_a.encode()).hexdigest()[:12]
        hash_b = hashlib.sha256(session_b.encode()).hexdigest()[:12]

        # The state file names include the session hash
        assert hash_a != hash_b

        expected_a = f"/tmp/claude-reread-tracker-{hash_a}.json"
        expected_b = f"/tmp/claude-reread-tracker-{hash_b}.json"

        # Run the hook with session_a to verify it creates the right file
        env_a = os.environ.copy()
        env_a["CLAUDE_SESSION_ID"] = session_a
        event = {"tool_name": "Read", "tool_input": {"file_path": "/tmp/test-file.py"}}
        subprocess.run(
            ["python3", str(HOOKS_DIR / "reread-before-edit.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
            env=env_a,
        )

        env_b = os.environ.copy()
        env_b["CLAUDE_SESSION_ID"] = session_b
        subprocess.run(
            ["python3", str(HOOKS_DIR / "reread-before-edit.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
            env=env_b,
        )

        # Both state files should exist and be different
        assert os.path.exists(expected_a)
        assert os.path.exists(expected_b)
        assert expected_a != expected_b

        # Cleanup
        for f in (expected_a, expected_b):
            try:
                os.unlink(f)
            except OSError:
                pass

    def test_edit_without_read_warns(self):
        """Editing a file never Read should produce a stale-context advisory."""
        session_id = "test-reread-warn"
        env = os.environ.copy()
        env["CLAUDE_SESSION_ID"] = session_id

        event = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/never-read.py"},
        }
        result = subprocess.run(
            ["python3", str(HOOKS_DIR / "reread-before-edit.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        parsed = json.loads(result.stdout)
        assert parsed["decision"] == "allow"
        assert "stale" in parsed["reason"].lower()

        # Cleanup
        h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
        try:
            os.unlink(f"/tmp/claude-reread-tracker-{h}.json")
        except OSError:
            pass
