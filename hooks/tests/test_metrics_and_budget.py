"""Tests for metrics-and-budget.py hook."""


class TestMetricsLogging:
    def test_normal_event_no_crash(self, run_hook, make_event):
        event = make_event("Bash", command="ls -la")
        result = run_hook("metrics-and-budget.py", event)
        assert result.returncode == 0

    def test_malformed_stdin_no_crash(self, run_hook):
        """Malformed stdin should not crash the hook."""
        import json
        import subprocess
        from pathlib import Path

        hooks_dir = Path("/Users/cevin/.claude/skills/coding-team/hooks")
        result = subprocess.run(
            ["python3", str(hooks_dir / "metrics-and-budget.py")],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_edit_event_no_crash(self, run_hook, make_event):
        event = make_event("Edit", file_path="/tmp/test.py", new_string="hello")
        result = run_hook("metrics-and-budget.py", event)
        assert result.returncode == 0
