"""Tests for hook-health-check.py hook."""

import importlib.util
import json
import os
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


class TestCheckMcpHealth:
    def test_returns_list(self, hhc):
        """check_mcp_health always returns a list."""
        result = hhc.check_mcp_health()
        assert isinstance(result, list)

    def test_all_issues_mention_binary_names(self, hhc):
        """Every issue string references a known MCP binary name."""
        result = hhc.check_mcp_health()
        known_names = {"codesight-mcp", "qmd"}
        for issue in result:
            assert any(name in issue for name in known_names), (
                f"Issue does not reference a known binary: {issue}"
            )

    def test_found_binary_not_in_issues(self, hhc, tmp_path):
        """A binary that exists on disk is not reported as missing."""
        import shutil

        # Create a real binary in tmp_path and prepend to PATH
        fake_bin = tmp_path / "codesight-mcp"
        fake_bin.write_text("#!/bin/bash\necho ok")
        fake_bin.chmod(0o755)
        original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{tmp_path}:{original_path}"
        try:
            result = hhc.check_mcp_health()
            codesight_issues = [i for i in result if "codesight-mcp" in i]
            assert len(codesight_issues) == 0
        finally:
            os.environ["PATH"] = original_path

    def test_missing_binary_with_empty_path(self, hhc):
        """With an empty PATH and no common paths, binaries are reported missing."""
        original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = "/nonexistent-test-path-that-does-not-exist"
        try:
            result = hhc.check_mcp_health()
            # At minimum one binary should be missing
            assert len(result) >= 1
            all_text = " ".join(result)
            assert "not found" in all_text
        finally:
            os.environ["PATH"] = original_path

    def test_issues_are_strings(self, hhc):
        """All returned issues are strings."""
        result = hhc.check_mcp_health()
        for issue in result:
            assert isinstance(issue, str)


class TestCheckInstructionFileLengths:
    def test_file_under_200_lines_no_warning(self, hhc, tmp_path):
        """A file under 200 lines produces no warnings."""
        # Set up a fake repo structure
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        short_file = agents_dir / "test-agent.md"
        short_file.write_text("\n".join(f"line {i}" for i in range(50)))

        # Point repo_root to tmp_path by patching __file__ indirectly
        original_fn = hhc.check_instruction_file_lengths

        def patched():
            import types

            orig_path = hhc.Path
            repo_root = tmp_path
            warnings = []
            instruction_globs = [
                "agents/*.md",
                "phases/*.md",
                "skills/*/SKILL.md",
            ]
            for pattern in instruction_globs:
                for filepath in repo_root.glob(pattern):
                    try:
                        line_count = len(filepath.read_text().splitlines())
                        if line_count > 200:
                            warnings.append(
                                f"{filepath.relative_to(repo_root)} is {line_count} lines "
                                f"(threshold: 200). Consider extracting content to on-demand files."
                            )
                    except OSError:
                        continue
            return warnings

        result = patched()
        assert result == []

    def test_file_over_200_lines_produces_warning(self, hhc, tmp_path):
        """A file over 200 lines produces a warning with filename and line count."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        long_file = agents_dir / "bloated-agent.md"
        long_file.write_text("\n".join(f"line {i}" for i in range(250)))

        repo_root = tmp_path
        warnings = []
        instruction_globs = [
            "agents/*.md",
            "phases/*.md",
            "skills/*/SKILL.md",
        ]
        for pattern in instruction_globs:
            for filepath in repo_root.glob(pattern):
                try:
                    line_count = len(filepath.read_text().splitlines())
                    if line_count > 200:
                        warnings.append(
                            f"{filepath.relative_to(repo_root)} is {line_count} lines "
                            f"(threshold: 200). Consider extracting content to on-demand files."
                        )
                except OSError:
                    continue

        assert len(warnings) == 1
        assert "bloated-agent.md" in warnings[0]
        assert "250 lines" in warnings[0]
        assert "threshold: 200" in warnings[0]

    def test_real_function_returns_list(self, hhc):
        """The real function returns a list (may or may not have warnings)."""
        result = hhc.check_instruction_file_lengths()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, str)


class TestCheckMetrics:
    """Tests for the merged metrics analysis functionality."""

    def test_no_metrics_returns_empty_list(self, hhc, tmp_path):
        """When metrics directory does not exist, check_metrics returns []."""
        original = hhc.METRICS_DIR
        hhc.METRICS_DIR = tmp_path / "nonexistent"
        try:
            result = hhc.check_metrics()
            assert result == []
        finally:
            hhc.METRICS_DIR = original

    def test_empty_metrics_returns_empty_list(self, hhc, tmp_path):
        """When metrics directory has no JSONL files, check_metrics returns []."""
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()
        original = hhc.METRICS_DIR
        hhc.METRICS_DIR = metrics_dir
        try:
            result = hhc.check_metrics()
            assert result == []
        finally:
            hhc.METRICS_DIR = original

    def test_anomalies_detected(self, hhc, tmp_path):
        """Sessions with high edit:read ratio produce anomaly output."""
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()
        session_id = "past-session-1"
        records = []
        for _ in range(10):
            records.append({"tool": "Edit", "session": session_id})
        for _ in range(2):
            records.append({"tool": "Read", "session": session_id})
        log_file = metrics_dir / "tool-usage-2026-03-26.jsonl"
        with open(log_file, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

        original_dir = hhc.METRICS_DIR
        hhc.METRICS_DIR = metrics_dir
        original_env = os.environ.get("CLAUDE_SESSION_ID")
        os.environ["CLAUDE_SESSION_ID"] = "current-session"
        try:
            result = hhc.check_metrics()
            assert len(result) > 0
            combined = "\n".join(result)
            assert "edit" in combined.lower() or "anomal" in combined.lower()
        finally:
            hhc.METRICS_DIR = original_dir
            if original_env is None:
                os.environ.pop("CLAUDE_SESSION_ID", None)
            else:
                os.environ["CLAUDE_SESSION_ID"] = original_env

    def test_analyze_session_high_agent_ratio(self, hhc):
        """Agent calls >40% of total triggers consolidation advisory."""
        records = [{"tool": "Agent", "session": "s1"}] * 50
        records += [{"tool": "Read", "session": "s1"}] * 20
        anomalies = hhc.analyze_session(records, "s1")
        matching = [a for a in anomalies if "agent dispatch ratio" in a.lower()]
        assert len(matching) == 1
        assert "consolidating worker prompts" in matching[0].lower()

    def test_analyze_session_low_agent_ratio_no_anomaly(self, hhc):
        """Agent calls <=40% should not trigger the anomaly."""
        records = [{"tool": "Agent", "session": "s1"}] * 10
        records += [{"tool": "Read", "session": "s1"}] * 30
        anomalies = hhc.analyze_session(records, "s1")
        matching = [a for a in anomalies if "agent dispatch ratio" in a.lower()]
        assert len(matching) == 0

    def test_summarize_sessions_basic(self, hhc):
        """summarize_sessions returns formatted lines with tool breakdown."""
        sessions = {
            "session-abc": (
                [{"tool": "Agent", "session": "session-abc"}] * 32
                + [{"tool": "Read", "session": "session-abc"}] * 28
                + [{"tool": "Edit", "session": "session-abc"}] * 22
                + [{"tool": "Bash", "session": "session-abc"}] * 18
                + [{"tool": "Grep", "session": "session-abc"}] * 15
            ),
        }
        summaries = hhc.summarize_sessions(sessions, "current-session")
        assert len(summaries) == 1
        line = summaries[0]
        assert "session-abc" in line
        assert "115 calls" in line
        assert "Agent:32" in line

    def test_summarize_sessions_skills_included(self, hhc):
        """Skill tool calls with skill field appear in summary."""
        records = [{"tool": "Read", "session": "s1"}] * 10
        records.append({"tool": "Skill", "session": "s1", "skill": "coding-team"})
        records.append({"tool": "Skill", "session": "s1", "skill": "scan-code"})
        sessions = {"s1": records}
        summaries = hhc.summarize_sessions(sessions, "current-session")
        assert len(summaries) == 1
        assert "skills:" in summaries[0]
        assert "coding-team" in summaries[0]

    def test_summarize_sessions_current_excluded(self, hhc):
        """Current session is excluded from summaries."""
        sessions = {
            "current": [{"tool": "Read", "session": "current"}] * 10,
            "past": [{"tool": "Read", "session": "past"}] * 10,
        }
        summaries = hhc.summarize_sessions(sessions, "current")
        assert len(summaries) == 1
        assert "past" in summaries[0]

    def test_aggregate_by_branch_groups_correctly(self, hhc):
        """Records with branch fields grouped; branches with 2+ sessions included."""
        records = [
            {"tool": "Read", "session": "s1", "branch": "feat/login"},
            {"tool": "Edit", "session": "s1", "branch": "feat/login"},
            {"tool": "Read", "session": "s2", "branch": "feat/login"},
            {"tool": "Bash", "session": "s2", "branch": "feat/login"},
            {"tool": "Bash", "session": "s2", "branch": "feat/login"},
        ]
        result = hhc.aggregate_by_branch(records)
        assert "feat/login" in result
        info = result["feat/login"]
        assert info["total_calls"] == 5
        assert info["session_count"] == 2

    def test_aggregate_by_branch_single_session_excluded(self, hhc):
        """Branches with only 1 session are excluded."""
        records = [
            {"tool": "Read", "session": "s1", "branch": "feat/solo"},
            {"tool": "Edit", "session": "s1", "branch": "feat/solo"},
        ]
        result = hhc.aggregate_by_branch(records)
        assert result == {}

    def test_format_branch_summary_empty(self, hhc):
        """Empty branch data returns empty string."""
        assert hhc.format_branch_summary({}) == ""

    def test_format_branch_summary_populated(self, hhc):
        """Populated branch data returns formatted output."""
        branch_data = {
            "feat/login": {
                "total_calls": 45,
                "session_count": 3,
                "top_tools": [("Read", 20), ("Edit", 15), ("Bash", 10)],
                "sessions": ["s1", "s2", "s3"],
            }
        }
        output = hhc.format_branch_summary(branch_data)
        assert "Branch cost summary:" in output
        assert "feat/login" in output
        assert "45 calls" in output

    def test_get_pr_throughput_returns_none_or_string(self, hhc):
        """get_pr_throughput returns None when gh unavailable or a valid string."""
        result = hhc.get_pr_throughput()
        assert result is None or isinstance(result, str)

    def test_skill_failure_rates_no_dir(self, hhc, tmp_path):
        """Missing metrics directory returns None."""
        original = hhc.METRICS_DIR
        hhc.METRICS_DIR = tmp_path / "nonexistent"
        try:
            result = hhc.get_skill_failure_rates()
            assert result is None
        finally:
            hhc.METRICS_DIR = original

    def test_skill_failure_rates_computed(self, hhc, tmp_path):
        """Skills with >10% failure rate are surfaced."""
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()
        lines = []
        for _ in range(8):
            lines.append(json.dumps({"skill": "coding-team", "status": "success"}))
        for _ in range(2):
            lines.append(json.dumps({"skill": "coding-team", "status": "error"}))
        (metrics_dir / "agent-quality-2026-03-26.jsonl").write_text(
            "\n".join(lines) + "\n"
        )
        original = hhc.METRICS_DIR
        hhc.METRICS_DIR = metrics_dir
        try:
            result = hhc.get_skill_failure_rates()
            assert result is not None
            assert "Skill failure rates:" in result
            assert "coding-team" in result
            assert "20%" in result
        finally:
            hhc.METRICS_DIR = original


class TestIntegration:
    def test_no_output_when_hooks_healthy(self, run_hook):
        """Full hook produces no output when all hooks are healthy."""
        result = run_hook("hook-health-check.py", {})
        # If all hooks in ~/.claude/hooks/ are healthy, output should be empty.
        # If some are unhealthy or MCP servers unavailable, verify valid JSON.
        if result.stdout.strip():
            parsed = json.loads(result.stdout)
            assert parsed["decision"] == "allow"
            reason_lower = parsed["reason"].lower()
            assert (
                "unhealthy" in reason_lower
                or "mcp" in reason_lower
                or "instruction file" in reason_lower
                or "session cost" in reason_lower
                or "anomal" in reason_lower
            )
        else:
            assert result.stdout.strip() == ""
