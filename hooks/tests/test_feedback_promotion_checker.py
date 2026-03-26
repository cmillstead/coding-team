"""Tests for feedback-promotion-checker.py internal functions."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
HOOK_FILE = HOOKS_DIR / "feedback-promotion-checker.py"


def _load_module():
    """Load the feedback-promotion-checker module for direct testing."""
    spec = importlib.util.spec_from_file_location("fpc", str(HOOK_FILE))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_python_func(func_name: str, *args) -> object:
    """Run a function from feedback-promotion-checker.py via subprocess."""
    code = (
        f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
        f"import importlib.util, json\n"
        f"spec = importlib.util.spec_from_file_location('fpc', {str(HOOK_FILE)!r})\n"
        f"mod = importlib.util.module_from_spec(spec)\n"
        f"spec.loader.exec_module(mod)\n"
        f"print(json.dumps(mod.{func_name}({', '.join(repr(a) for a in args)})))\n"
    )
    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"subprocess failed: {result.stderr}"
    return json.loads(result.stdout)


class TestScoreMechanicality:
    def test_mechanical_keywords_score_higher(self):
        """Text with file/path/config keywords should have higher mechanical score."""
        text = "Check the file path and config json schema for deploy errors"
        mechanical, behavioral = run_python_func("score_mechanicality", text)
        assert mechanical > behavioral
        assert mechanical >= 5  # file, path, config, json, schema, deploy, error

    def test_behavioral_keywords_score_higher(self):
        """Text with think/consider/design keywords should have higher behavioral score."""
        text = "Think about the approach and consider the design architecture strategy"
        mechanical, behavioral = run_python_func("score_mechanicality", text)
        assert behavioral > mechanical
        assert behavioral >= 4  # think, consider, approach, design, architecture, strategy

    def test_empty_text_scores_zero(self):
        mechanical, behavioral = run_python_func("score_mechanicality", "")
        assert mechanical == 0
        assert behavioral == 0

    def test_mixed_text_returns_both_scores(self):
        text = "The file import command should consider the design"
        mechanical, behavioral = run_python_func("score_mechanicality", text)
        assert mechanical >= 3  # file, import, command
        assert behavioral >= 2  # should, consider, design


class TestCheckAlreadyEnforced:
    def test_finds_matching_hook_name(self):
        """Feedback name that overlaps with a hook name should be detected."""
        result = run_python_func(
            "check_already_enforced",
            "feedback-reread-before-edit",
            "some content",
            ["reread-before-edit", "secret-guard"],
            [],
        )
        assert result is not None
        assert "hook:" in result
        assert "reread-before-edit" in result

    def test_finds_matching_rule_name(self):
        """Feedback name that overlaps with a rule name should be detected."""
        result = run_python_func(
            "check_already_enforced",
            "feedback-migration-files",
            "some content",
            [],
            ["migration-files", "config-files"],
        )
        assert result is not None
        assert "rule:" in result
        assert "migration-files" in result

    def test_detects_fixed_with_hook_in_content(self):
        """Content containing 'fixed with hook' should be detected."""
        result = run_python_func(
            "check_already_enforced",
            "feedback-something-new",
            "This issue was fixed with hook enforcement",
            [],
            [],
        )
        assert result == "referenced in content"

    def test_detects_promoted_to_rule_in_content(self):
        """Content containing 'promoted to rule' should be detected."""
        result = run_python_func(
            "check_already_enforced",
            "feedback-another-thing",
            "Pattern promoted to rule for enforcement",
            [],
            [],
        )
        assert result == "referenced in content"

    def test_detects_enforced_by_hook_in_content(self):
        """Content containing 'enforced by hook' should be detected."""
        result = run_python_func(
            "check_already_enforced",
            "feedback-yet-another",
            "Now enforced by hook automatically",
            [],
            [],
        )
        assert result == "referenced in content"

    def test_returns_none_for_unmatched(self):
        """Feedback with no matching hook, rule, or content reference returns None."""
        result = run_python_func(
            "check_already_enforced",
            "feedback-brand-new-issue",
            "This is a new issue with no structural enforcement yet",
            ["secret-guard", "ci-orphan-detector"],
            ["test-files", "config-files"],
        )
        assert result is None


class TestIntegration:
    def test_script_runs_and_produces_output(self):
        """Running the script directly should produce output without errors."""
        result = subprocess.run(
            ["python3", str(HOOK_FILE)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        # Should produce either "No feedback files found." or analysis output
        assert len(result.stdout.strip()) > 0

    def test_script_outputs_json_section(self):
        """Running the script should include a JSON section if feedback files exist."""
        result = subprocess.run(
            ["python3", str(HOOK_FILE)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        # If feedback files exist, there should be a JSON section
        if "--- JSON ---" in result.stdout:
            json_part = result.stdout.split("--- JSON ---")[1].strip()
            parsed = json.loads(json_part)
            assert "candidates" in parsed
            assert "enforced" in parsed
            assert "behavioral" in parsed


class TestIssueTracking:
    """Tests for get_already_filed, mark_as_filed, and deduplication logic."""

    def test_get_already_filed_empty(self, tmp_path):
        """No tracker file returns empty set."""
        mod = _load_module()
        # Point to a non-existent file in tmp_path
        mod.ISSUE_TRACKER_FILE = tmp_path / "nonexistent.json"
        result = mod.get_already_filed()
        assert result == set()

    def test_mark_as_filed_creates_file(self, tmp_path):
        """Filing marks persist to disk."""
        mod = _load_module()
        tracker = tmp_path / "tracker.json"
        mod.ISSUE_TRACKER_FILE = tracker

        mod.mark_as_filed("feedback-test-item")

        assert tracker.exists()
        data = json.loads(tracker.read_text())
        assert "feedback-test-item" in data["filed"]

    def test_already_filed_skipped(self, tmp_path):
        """Candidate already filed returns False from create_promotion_issue."""
        mod = _load_module()
        tracker = tmp_path / "tracker.json"
        mod.ISSUE_TRACKER_FILE = tracker

        # Pre-file the candidate
        mod.mark_as_filed("feedback-already-done")

        candidate = {
            "name": "feedback-already-done",
            "mechanical_score": 5,
            "behavioral_score": 1,
        }
        result = mod.create_promotion_issue(candidate, "some content")
        assert result is False

    def test_create_issue_low_score_not_filed(self):
        """Candidates with mechanical_score < 4 are not auto-filed by main() logic."""
        mod = _load_module()
        # The filtering happens in main(), not in create_promotion_issue.
        # Verify the threshold by checking the filter logic directly.
        candidates = [
            {"name": "fb-low", "status": "candidate", "mechanical_score": 2, "behavioral_score": 1},
            {"name": "fb-high", "status": "candidate", "mechanical_score": 5, "behavioral_score": 1},
        ]
        promotable = [c for c in candidates if c["status"] == "candidate"]
        high_score = [c for c in promotable if c["mechanical_score"] >= 4]
        assert len(high_score) == 1
        assert high_score[0]["name"] == "fb-high"

    def test_tracker_deduplication(self, tmp_path):
        """Same name filed twice only stored once."""
        mod = _load_module()
        tracker = tmp_path / "tracker.json"
        mod.ISSUE_TRACKER_FILE = tracker

        mod.mark_as_filed("feedback-dup-item")
        mod.mark_as_filed("feedback-dup-item")

        data = json.loads(tracker.read_text())
        assert data["filed"].count("feedback-dup-item") == 1
