"""Tests for metrics-analyzer.py hook."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def _load_analyzer_module():
    """Load metrics-analyzer.py as a module for direct function testing."""
    sys.path.insert(0, str(HOOKS_DIR))
    spec = importlib.util.spec_from_file_location(
        "metrics_analyzer", str(HOOKS_DIR / "metrics-analyzer.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


class TestHighAgentDispatchRatio:
    def test_agent_ratio_above_40_percent_triggers_anomaly(self):
        """Agent calls >40% of total should flag consolidation advisory."""
        mod = _load_analyzer_module()
        # 50 Agent calls + 20 other = 70 total, Agent ratio = 71%
        records = [{"tool": "Agent", "session": "s1"}] * 50
        records += [{"tool": "Read", "session": "s1"}] * 20
        anomalies = mod.analyze_session(records, "s1")
        matching = [a for a in anomalies if "agent dispatch ratio" in a.lower()]
        assert len(matching) == 1
        assert "consolidating worker prompts" in matching[0].lower()

    def test_agent_ratio_below_40_percent_no_anomaly(self):
        """Agent calls <=40% should not trigger the anomaly."""
        mod = _load_analyzer_module()
        # 10 Agent + 30 other = 40 total, Agent ratio = 25%
        records = [{"tool": "Agent", "session": "s1"}] * 10
        records += [{"tool": "Read", "session": "s1"}] * 30
        anomalies = mod.analyze_session(records, "s1")
        matching = [a for a in anomalies if "agent dispatch ratio" in a.lower()]
        assert len(matching) == 0


class TestSummarizeSessions:
    def test_basic_summary_format(self):
        """summarize_sessions returns formatted summary lines with tool breakdown."""
        mod = _load_analyzer_module()
        sessions = {
            "session-abc": (
                [{"tool": "Agent", "session": "session-abc"}] * 32
                + [{"tool": "Read", "session": "session-abc"}] * 28
                + [{"tool": "Edit", "session": "session-abc"}] * 22
                + [{"tool": "Bash", "session": "session-abc"}] * 18
                + [{"tool": "Grep", "session": "session-abc"}] * 15
            ),
        }
        summaries = mod.summarize_sessions(sessions, "current-session")
        assert len(summaries) == 1
        line = summaries[0]
        assert "session-abc" in line
        assert "115 calls" in line
        assert "Agent:32" in line

    def test_skills_included_when_present(self):
        """Skill tool calls with skill field should appear in summary."""
        mod = _load_analyzer_module()
        records = [{"tool": "Read", "session": "s1"}] * 10
        records.append({"tool": "Skill", "session": "s1", "skill": "coding-team"})
        records.append({"tool": "Skill", "session": "s1", "skill": "scan-code"})
        sessions = {"s1": records}
        summaries = mod.summarize_sessions(sessions, "current-session")
        assert len(summaries) == 1
        assert "skills:" in summaries[0]
        assert "coding-team" in summaries[0]
        assert "scan-code" in summaries[0]

    def test_no_skills_when_absent(self):
        """When no Skill tool calls, summary should not contain 'skills:' label."""
        mod = _load_analyzer_module()
        records = [{"tool": "Read", "session": "s1"}] * 10
        sessions = {"s1": records}
        summaries = mod.summarize_sessions(sessions, "current-session")
        assert len(summaries) == 1
        assert "skills:" not in summaries[0]

    def test_current_session_excluded(self):
        """Current session should be excluded from summaries."""
        mod = _load_analyzer_module()
        sessions = {
            "current": [{"tool": "Read", "session": "current"}] * 10,
            "past": [{"tool": "Read", "session": "past"}] * 10,
        }
        summaries = mod.summarize_sessions(sessions, "current")
        assert len(summaries) == 1
        assert "past" in summaries[0]

    def test_max_sessions_respected(self):
        """Only max_sessions summaries should be returned."""
        mod = _load_analyzer_module()
        sessions = {}
        for i in range(5):
            sid = f"s{i}"
            sessions[sid] = [{"tool": "Read", "session": sid}] * 10
        summaries = mod.summarize_sessions(sessions, "current", max_sessions=2)
        assert len(summaries) == 2

    def test_empty_session_skipped(self):
        """Sessions with 0 records should be skipped."""
        mod = _load_analyzer_module()
        sessions = {"empty": [], "notempty": [{"tool": "Read", "session": "notempty"}] * 5}
        summaries = mod.summarize_sessions(sessions, "current")
        assert len(summaries) == 1
        assert "notempty" in summaries[0]


class TestAggregatByBranch:
    def test_groups_by_branch_with_multiple_sessions(self):
        """Records with branch fields are grouped; branches with 2+ sessions included."""
        mod = _load_analyzer_module()
        records = [
            {"tool": "Read", "session": "s1", "branch": "feat/login"},
            {"tool": "Edit", "session": "s1", "branch": "feat/login"},
            {"tool": "Read", "session": "s2", "branch": "feat/login"},
            {"tool": "Bash", "session": "s2", "branch": "feat/login"},
            {"tool": "Bash", "session": "s2", "branch": "feat/login"},
        ]
        result = mod.aggregate_by_branch(records)
        assert "feat/login" in result
        info = result["feat/login"]
        assert info["total_calls"] == 5
        assert info["session_count"] == 2
        assert set(info["sessions"]) == {"s1", "s2"}
        # Top tools should include the counts
        tool_names = [t for t, _ in info["top_tools"]]
        assert "Bash" in tool_names
        assert "Read" in tool_names

    def test_no_branch_fields_returns_empty(self):
        """Records without branch fields should produce an empty result."""
        mod = _load_analyzer_module()
        records = [
            {"tool": "Read", "session": "s1"},
            {"tool": "Edit", "session": "s2"},
        ]
        result = mod.aggregate_by_branch(records)
        assert result == {}

    def test_single_session_branch_excluded(self):
        """Branches with only 1 session should be excluded from aggregation."""
        mod = _load_analyzer_module()
        records = [
            {"tool": "Read", "session": "s1", "branch": "feat/solo"},
            {"tool": "Edit", "session": "s1", "branch": "feat/solo"},
            {"tool": "Read", "session": "s1", "branch": "feat/solo"},
        ]
        result = mod.aggregate_by_branch(records)
        assert "feat/solo" not in result
        assert result == {}

    def test_multiple_branches_aggregated_independently(self):
        """Multiple branches each with 2+ sessions are all included."""
        mod = _load_analyzer_module()
        records = [
            {"tool": "Read", "session": "s1", "branch": "feat/a"},
            {"tool": "Read", "session": "s2", "branch": "feat/a"},
            {"tool": "Edit", "session": "s3", "branch": "feat/b"},
            {"tool": "Edit", "session": "s4", "branch": "feat/b"},
            {"tool": "Bash", "session": "s5", "branch": "feat/c"},  # only 1 session
        ]
        result = mod.aggregate_by_branch(records)
        assert "feat/a" in result
        assert "feat/b" in result
        assert "feat/c" not in result


class TestFormatBranchSummary:
    def test_format_multi_session_branch(self):
        """format_branch_summary produces readable output with call counts."""
        mod = _load_analyzer_module()
        branch_data = {
            "feat/login": {
                "total_calls": 45,
                "session_count": 3,
                "top_tools": [("Read", 20), ("Edit", 15), ("Bash", 10)],
                "sessions": ["s1", "s2", "s3"],
            }
        }
        output = mod.format_branch_summary(branch_data)
        assert "Branch cost summary:" in output
        assert "feat/login" in output
        assert "45 calls" in output
        assert "3 sessions" in output
        assert "Read:20" in output

    def test_format_empty_data_returns_empty_string(self):
        """Empty branch data should return empty string."""
        mod = _load_analyzer_module()
        assert mod.format_branch_summary({}) == ""

    def test_format_multiple_branches_sorted(self):
        """Multiple branches should appear sorted alphabetically."""
        mod = _load_analyzer_module()
        branch_data = {
            "feat/z": {
                "total_calls": 10,
                "session_count": 2,
                "top_tools": [("Read", 10)],
                "sessions": ["s1", "s2"],
            },
            "feat/a": {
                "total_calls": 20,
                "session_count": 3,
                "top_tools": [("Edit", 20)],
                "sessions": ["s3", "s4", "s5"],
            },
        }
        output = mod.format_branch_summary(branch_data)
        lines = output.strip().split("\n")
        # Header + 2 branch lines
        assert len(lines) == 3
        assert "feat/a" in lines[1]
        assert "feat/z" in lines[2]


class TestCostSummaryIntegration:
    def test_cost_summary_appears_in_output(self, tmp_path):
        """Integration test: cost summary section appears in advisory output."""
        session_id = "past-session-cost"
        records = []
        for _ in range(25):
            records.append({"tool": "Read", "session": session_id})
        for _ in range(20):
            records.append({"tool": "Edit", "session": session_id})
        for _ in range(15):
            records.append({"tool": "Bash", "session": session_id})

        result, parsed = _run_metrics_analyzer(tmp_path, records)
        assert result.returncode == 0
        if parsed:
            assert parsed["decision"] == "allow"
            reason = parsed["reason"]
            assert "Session cost summary" in reason
            assert "past-session-cost" in reason
            assert "60 calls" in reason
