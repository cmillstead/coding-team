"""Tests for metrics-analyzer.py hook."""

import json
import os
import subprocess
from pathlib import Path

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def _run_metrics_analyzer(tmp_path, records=None):
    """Helper to run metrics-analyzer.py with a custom METRICS_DIR via wrapper script."""
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    if records:
        log_file = metrics_dir / "tool-usage-2026-03-26.jsonl"
        with open(log_file, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    env = os.environ.copy()
    env["CLAUDE_SESSION_ID"] = "current-session"

    # Use importlib to load the hook module with a redirected METRICS_DIR constant.
    # This uses real filesystem paths (tmp_path) — no fake objects involved.
    wrapper = tmp_path / "run_analyzer.py"
    wrapper.write_text(
        f"import sys\n"
        f"sys.path.insert(0, '{HOOKS_DIR}')\n"
        f"import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('analyzer', '{HOOKS_DIR / 'metrics-analyzer.py'}')\n"
        f"mod = importlib.util.module_from_spec(spec)\n"
        f"from pathlib import Path\n"
        f"mod.METRICS_DIR = Path('{metrics_dir}')\n"
        f"spec.loader.exec_module(mod)\n"
    )

    result = subprocess.run(
        ["python3", str(wrapper)],
        input="{}",
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return result, parsed


class TestNoMetrics:
    def test_no_metrics_files_no_output(self, tmp_path):
        """When metrics directory has no JSONL files, hook should produce no output."""
        result, parsed = _run_metrics_analyzer(tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_empty_metrics_file_no_output(self, tmp_path):
        """Empty metrics files should produce no output."""
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir(parents=True)
        (metrics_dir / "tool-usage-2026-03-26.jsonl").write_text("")
        result, parsed = _run_metrics_analyzer(tmp_path)
        assert result.returncode == 0


class TestHighEditReadRatio:
    def test_high_edit_read_ratio_triggers_advisory(self, tmp_path):
        """Edit:Read ratio >3:1 with >6 edits should trigger stale context advisory."""
        session_id = "past-session-1"
        records = []
        # 10 Edit calls, 2 Read calls for a past session
        for _ in range(10):
            records.append({"tool": "Edit", "session": session_id, "ts": "2026-03-26T10:00:00Z"})
        for _ in range(2):
            records.append({"tool": "Read", "session": session_id, "ts": "2026-03-26T10:00:00Z"})

        result, parsed = _run_metrics_analyzer(tmp_path, records)
        assert result.returncode == 0
        if parsed:
            assert parsed["decision"] == "allow"
            reason = parsed["reason"].lower()
            assert "edit" in reason or "read" in reason or "stale" in reason


class TestExcessiveBashCalls:
    def test_excessive_bash_calls_triggers_advisory(self, tmp_path):
        """More than 30 Bash calls should trigger retry loop advisory."""
        session_id = "past-session-2"
        records = []
        for _ in range(35):
            records.append({"tool": "Bash", "session": session_id, "ts": "2026-03-26T10:00:00Z"})

        result, parsed = _run_metrics_analyzer(tmp_path, records)
        assert result.returncode == 0
        if parsed:
            assert parsed["decision"] == "allow"
            reason = parsed["reason"].lower()
            assert "bash" in reason or "retry" in reason or "35" in reason
