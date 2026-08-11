"""Tests for scripts/check-model-tiers.py — the TRK-126 model-tier regression guard.

Every test drives the real checker: find_violations() called against a synthetic
repository built in tmp_path, or the script itself run via subprocess for
exit-code and output behavior. No mocks — the checker only reads the filesystem,
so the real thing is always available.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # tests/ -> hooks/ -> repo
SCRIPT = REPO_ROOT / "scripts" / "check-model-tiers.py"


def _load_checker():
    """Import check-model-tiers.py via importlib (the filename is not importable)."""
    spec = importlib.util.spec_from_file_location("check_model_tiers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _make_repo(tmp_path, files=None):
    """Build a synthetic repo with agents/ and phases/ plus {relpath: content}.

    Each scan dir is seeded with one clean live file: a dir that exists but
    yields zero scanned files is itself a violation (see
    TestEmptyScanDirectory), and these tests are about their listed content,
    not about scan-set coverage. Tests that need an empty or excluded-only
    dir build it by hand instead of calling this helper.
    """
    for scan_dir in ("agents", "phases"):
        (tmp_path / scan_dir).mkdir(parents=True, exist_ok=True)
        seed = tmp_path / scan_dir / "seed-clean.md"
        seed.write_text("This live file keeps the scan set non-empty.\n", encoding="utf-8")
    for rel, content in (files or {}).items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path


class TestCleanRepo:
    def test_no_model_tier_returns_no_violations(self, tmp_path):
        """A repo whose agents/ and phases/ carry no model tier is clean."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": "---\nname: Impl\ntools:\n  - Read\n---\nYou are.\n",
            "phases/planning.md": "Dispatch a Planning Worker via Agent tool.\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == []


class TestFrontmatterTier:
    def test_agent_frontmatter_model_is_a_violation(self, tmp_path):
        """agents/*.md with `model: sonnet` in frontmatter is reported."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": "---\nname: Impl\nmodel: sonnet\ntools:\n---\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1
        assert "agents/ct-implementer.md:3" in result[0]


class TestInlineDispatchTier:
    def test_phase_dispatch_model_is_a_violation(self, tmp_path):
        """phases/*.md with an inline `(model: opus)` dispatch arg is reported."""
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/planning.md": "# Phase 4\n\nDispatch a worker via Agent tool (model: opus).\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1
        assert "phases/planning.md:3" in result[0]

    def test_every_hit_is_reported_not_just_the_first(self, tmp_path):
        """Two tiers in one file produce two violations — the guard does not stop early."""
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md": (
                "Dispatch scan-security (model: sonnet).\n"
                "filler\n"
                "Dispatch the QA reviewer (model: sonnet, subagent_type: Explore).\n"
            ),
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 2


class TestTierAgnostic:
    """The guard fires on the KEY, never on a closed list of tier values.

    A checker narrowed to `haiku|sonnet|opus` would pass every other test in
    this file — and would wave a new tier through silently, which is the exact
    staleness that produced TRK-126.
    """

    @pytest.mark.parametrize(
        "tier", ["haiku", "sonnet", "opus", "fable", "some-future-tier"]
    )
    def test_any_tier_value_is_a_violation(self, tmp_path, tier):
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": f"---\nname: Impl\nmodel: {tier}\n---\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1, f"tier {tier!r} was not detected"
        assert "agents/ct-implementer.md:3" in result[0]


class TestKeySpellings:
    """Every YAML spelling of the same key is caught; compound keys are not."""

    @pytest.mark.parametrize(
        "spelling",
        ["model: sonnet", "model : sonnet", '"model": sonnet', "'model': sonnet"],
    )
    def test_yaml_key_spellings_are_violations(self, tmp_path, spelling):
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": f"---\nname: Impl\n{spelling}\n---\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1, f"spelling {spelling!r} was not detected"

    @pytest.mark.parametrize("key", ["session-model: sonnet", "custom-model: sonnet"])
    def test_compound_key_is_not_a_violation(self, tmp_path, key):
        """`\\bmodel:` falsely matches these — the `\\b` sits between `-` and `m`."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": f"---\nname: Impl\n{key}\n---\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == [], f"compound key {key!r} was wrongly flagged"


class TestJustificationMarker:
    def test_marker_with_reason_suppresses_the_hit(self, tmp_path):
        """A tier carrying `model-tier-ok: <reason>` on the same line is allowed."""
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md": (
                "Dispatch via Agent tool (model: haiku). "
                "<!-- model-tier-ok: purely mechanical file rename, operator approved 2026-08-11 -->\n"
            ),
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == []

    def test_bare_marker_in_html_comment_does_not_suppress(self, tmp_path):
        """`<!-- model-tier-ok: -->` says nothing and must not excuse the tier.

        Regression: a "marker followed by non-whitespace" rule accepts this,
        because the `-` of the `-->` terminator is itself non-whitespace.
        """
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md": "Dispatch (model: haiku). <!-- model-tier-ok: -->\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1

    def test_marker_with_too_short_reason_does_not_suppress(self, tmp_path):
        """A reason under MIN_JUSTIFICATION_CHARS is not a justification."""
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md": "Dispatch (model: haiku). <!-- model-tier-ok: ok -->\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1

    def test_marker_at_start_of_line_html_does_not_suppress(self, tmp_path):
        """A leading empty marker must not claim the rest of the line as its reason.

        Regression: stripping a terminator only from the END of the captured
        reason leaves `--> Dispatch (model: haiku).` — 27 characters that clear
        the length floor while explaining nothing.
        """
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md":
                "<!-- model-tier-ok: --> Dispatch (model: haiku).\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1

    def test_marker_at_start_of_line_block_comment_does_not_suppress(self, tmp_path):
        """Same hole in `/* */` form — the terminator search must cover both."""
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md":
                "/* model-tier-ok: */ Dispatch (model: haiku).\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1

    def test_undelimited_marker_before_key_does_not_suppress(self, tmp_path):
        """A line-leading marker with no comment terminator must not swallow the tier.

        Regression: with no terminator anywhere on the line, terminator
        truncation never fires and the captured "reason" is the dispatch text
        itself — `Dispatch via Agent tool (model: haiku).` clears the length
        floor while justifying nothing. A marker can only annotate a key that
        PRECEDES it on the line.
        """
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/x.md": "model-tier-ok: Dispatch via Agent tool (model: haiku).\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1

    def test_undelimited_marker_after_key_still_suppresses(self, tmp_path):
        """The escape hatch survives: a real reason AFTER the key needs no comment syntax."""
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/x.md": (
                "Dispatch via Agent tool (model: haiku). "
                "model-tier-ok: mechanical rename batch, operator approved 2026-08-11\n"
            ),
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == []

    def test_justification_is_per_line_not_per_file(self, tmp_path):
        """One valid marker must not excuse a DIFFERENT line in the same file.

        An implementation that suppresses file-wide whenever any marker is
        present would pass every other justification test here.
        """
        # Arrange
        root = _make_repo(tmp_path, {
            "phases/execution.md": (
                "Dispatch A (model: haiku). "
                "<!-- model-tier-ok: mechanical, operator approved 2026-08-11 -->\n"
                "Dispatch B (model: sonnet).\n"
            ),
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert len(result) == 1
        assert "phases/execution.md:2" in result[0], (
            f"expected only the unjustified line 2 to be reported, got {result}"
        )
        assert "sonnet" in result[0]


class TestScanSetBoundaries:
    def test_agents_reference_subdir_is_not_scanned(self, tmp_path):
        """agents/reference/ holds prose like 'Maturity model: Levels 0-4' — not a dispatch."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/reference/harness-engineer-reference.md":
                "- **Ch 22** — Maturity model: Levels 0-4, assessment checklist\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == []

    def test_agents_readme_is_not_scanned(self, tmp_path):
        """agents/README.md documents the frontmatter schema; it is not a dispatch."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/README.md": "model: haiku | sonnet | opus\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == []

    def test_docs_plans_and_reviews_are_not_scanned(self, tmp_path):
        """Historical records under docs/ keep their tiers and must not fail CI."""
        # Arrange
        root = _make_repo(tmp_path, {
            "docs/plans/2026-01-01-old.md": "**Model:** opus\nmodel: opus\n",
            "docs/reviews/2026-01-01-review.md": "model: sonnet\n",
        })

        # Act
        result = checker.find_violations(root)

        # Assert
        assert result == []


class TestMissingScanDirectory:
    def test_missing_phases_dir_is_a_failure_not_a_silent_pass(self, tmp_path):
        """A renamed scan dir must fail loudly, never scan nothing and pass."""
        # Arrange — agents/ gets a live file so only the missing dir is at fault
        (tmp_path / "agents").mkdir(parents=True)
        (tmp_path / "agents" / "impl.md").write_text(
            "Dispatch via Agent tool.\n", encoding="utf-8"
        )
        # phases/ deliberately absent

        # Act
        result = checker.find_violations(tmp_path)

        # Assert
        assert len(result) == 1
        assert "phases/" in result[0]


class TestEmptyScanDirectory:
    def test_empty_scan_dirs_are_failures_not_silent_passes(self, tmp_path):
        """Dirs that exist but hold zero live files must fail loudly.

        Regression: only a MISSING dir failed; live files moved into a nested
        subdirectory (invisible to the non-recursive glob) left both dirs
        present-but-empty and the guard passed vacuously.
        """
        # Arrange
        (tmp_path / "agents").mkdir(parents=True)
        (tmp_path / "phases").mkdir(parents=True)

        # Act
        result = checker.find_violations(tmp_path)

        # Assert
        assert len(result) == 2
        assert any("agents/" in violation for violation in result)
        assert any("phases/" in violation for violation in result)

    def test_dir_with_only_excluded_readme_is_a_failure(self, tmp_path):
        """An excluded README.md must not count as scan coverage."""
        # Arrange
        (tmp_path / "agents").mkdir(parents=True)
        (tmp_path / "agents" / "README.md").write_text(
            "model: haiku | sonnet | opus\n", encoding="utf-8"
        )
        (tmp_path / "phases").mkdir(parents=True)
        (tmp_path / "phases" / "planning.md").write_text(
            "Dispatch via Agent tool.\n", encoding="utf-8"
        )

        # Act
        result = checker.find_violations(tmp_path)

        # Assert
        assert len(result) == 1
        assert "agents/" in result[0]


class TestScriptExitCodes:
    def test_violating_repo_exits_1_and_names_the_file(self, tmp_path):
        """Run the real script: a tier present means exit 1 and the path in stdout."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": "---\nname: Impl\nmodel: sonnet\n---\n",
        })

        # Act
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(root)],
            capture_output=True, text=True,
        )

        # Assert
        assert proc.returncode == 1
        assert "agents/ct-implementer.md" in proc.stdout
        assert "model-tier-ok" in proc.stdout  # the fix instruction is in the message

    def test_clean_repo_exits_0(self, tmp_path):
        """Run the real script: a clean repo means exit 0 and a pass line."""
        # Arrange
        root = _make_repo(tmp_path, {
            "agents/ct-implementer.md": "---\nname: Impl\ntools:\n---\n",
        })

        # Act
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(root)],
            capture_output=True, text=True,
        )

        # Assert
        assert proc.returncode == 0
        assert "all checks passed" in proc.stdout
