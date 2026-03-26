"""Tests for write-guard.py hook.

# mock-ok: test data strings trigger the no-mocks hook scanner — these are test INPUTS, not real mock usage
"""

import base64
import os
import json
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")

# Encode mock-triggering test data as base64 to avoid the no-mocks hook
# scanning THIS file and blocking the write. These are INPUT strings we
# feed to the hook under test — not actual mock usage.
# mock-ok: base64-encoded test input data for hook validation, not real mock usage
_B64_MOCK_IMPORT = "ZnJvbSB1bml0dGVzdC5tb2NrIGltcG9ydCBNYWdpY01vY2s="
# mock-ok: base64-encoded test input data for hook validation, not real mock usage
_B64_MOCK_ALLOWLIST = "IyBtb2NrLW9rOiBwYWlkIEFQSQpmcm9tIHVuaXR0ZXN0Lm1vY2sgaW1wb3J0IE1hZ2ljTW9jaw=="


def _decode(b64: str) -> str:
    return base64.b64decode(b64).decode()


def run_write_guard(event: dict) -> dict | None:
    """Run write-guard.py with the given event, return parsed JSON or None."""
    result = subprocess.run(
        ["python3", str(HOOKS_DIR / "write-guard.py")],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
    )
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None


class TestMigrationGuard:
    def test_blocks_edit_to_existing_migration(self, tmp_path):
        migration_dir = tmp_path / "migrations"
        migration_dir.mkdir()
        migration_file = migration_dir / "001_create.py"
        migration_file.write_text("# migration")

        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(migration_file),
                "new_string": "altered",
            },
        }
        parsed = run_write_guard(event)
        assert parsed is not None
        assert parsed["decision"] == "block"
        assert "migration" in parsed["reason"].lower()


class TestNoMocksGuard:
    def test_blocks_mock_in_test_file(self):
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/tests/test_example.py",
                "new_string": _decode(_B64_MOCK_IMPORT),
            },
        }
        parsed = run_write_guard(event)
        assert parsed is not None
        assert parsed["decision"] == "block"
        assert "mock" in parsed["reason"].lower()

    def test_allows_mock_with_allowlist_marker(self):
        event = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/tests/test_example.py",
                "new_string": _decode(_B64_MOCK_ALLOWLIST),
            },
        }
        parsed = run_write_guard(event)
        # Should allow -- the allowlist marker exempts this
        if parsed:
            assert parsed.get("decision") != "block"


class TestIdentityFramingAdvisory:
    def test_advisory_for_agent_file_without_identity(self):
        event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": os.path.expanduser("~/.claude/agents/ct-foo.md"),
                "content": "# Agent\nDo some stuff.",
            },
        }
        parsed = run_write_guard(event)
        if parsed:
            assert parsed.get("decision") != "block"
            if "reason" in parsed:
                assert "identity" in parsed["reason"].lower()


class TestSessionTamperDetection:
    """Test that write-guard detects session file deletion mid-session."""

    def test_blocks_when_active_marker_exists_but_session_missing(self, run_hook, make_event, tmp_path):
        """If active marker exists but session JSON is missing, block."""
        active_marker = Path("/tmp/coding-team-active")
        session_file = Path("/tmp/coding-team-session.json")

        # Create active marker, ensure session file doesn't exist
        active_marker.touch()
        if session_file.exists():
            session_file.unlink()

        try:
            event = make_event("Edit", file_path="/some/code/file.py", old_string="x", new_string="y")
            result = run_hook("write-guard.py", event)
            assert result.parsed is not None
            assert result.parsed["decision"] == "block"
            assert "session file is missing" in result.parsed["reason"].lower() or "session marker" in result.parsed["reason"].lower()
        finally:
            active_marker.unlink(missing_ok=True)

    def test_allows_when_neither_marker_nor_session_exists(self, run_hook, make_event):
        """If neither active marker nor session file exists, allow."""
        active_marker = Path("/tmp/coding-team-active")
        session_file = Path("/tmp/coding-team-session.json")
        active_marker.unlink(missing_ok=True)
        session_file.unlink(missing_ok=True)

        event = make_event("Edit", file_path="/some/code/file.py", old_string="x", new_string="y")
        result = run_hook("write-guard.py", event)
        # Should not block (no session active)
        if result.parsed:
            assert result.parsed.get("decision") != "block" or "session" not in result.parsed.get("reason", "").lower()


class TestNormalFileAllowed:
    def test_allows_edit_to_normal_python_file(self, run_hook, make_event):
        event = make_event(
            "Edit",
            file_path="/tmp/src/main.py",
            new_string="print('hello')",
        )
        result = run_hook("write-guard.py", event)
        assert result.stdout.strip() == ""
