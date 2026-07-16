"""Regression test: llm_eval tests must be gated (skipped) by default.

Root cause: pytest.ini declares the ``llm_eval`` marker as "skipped by
default" and test_skill_evals.py's docstring claims the eval harness is
"gated behind @pytest.mark.llm_eval — skipped unless explicitly requested",
but no mechanism actually implemented that skip. A bare ``pytest`` invocation
collected AND RAN the 7 ``TestSkillEvalHarness.test_skill_routing`` cases,
which shell out to the real ``claude`` CLI and fail non-deterministically
(subprocess timeouts).

This test proves the gate added to conftest.py (``--run-llm-eval`` opt-in +
``pytest_collection_modifyitems``) actually works, via a real pytest
subprocess (no mocks). The default-run assertion relies on the skip marker
being attached during collection, which prevents the test body (and thus the
``claude`` CLI subprocess call) from ever executing — so it stays fast and
deterministic. The opt-in assertion uses ``--collect-only`` so it never
spawns the real ``claude`` CLI either.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET = "hooks/tests/test_skill_evals.py"


def _run_pytest(*extra_args: str) -> subprocess.CompletedProcess[str]:
    """Run pytest against TARGET in a subprocess and return the completed process."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", TARGET, *extra_args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_llm_eval_tests_skipped_by_default():
    """A bare pytest run must skip the llm_eval routing cases, not execute them.

    Skipped items never call the test body, so this never spawns the real
    claude CLI and stays fast/deterministic.
    """
    result = _run_pytest("-k", "test_skill_routing", "-q", "-rs")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "7 skipped" in result.stdout, result.stdout
    assert "failed" not in result.stdout.lower(), result.stdout
    assert "llm_eval" in result.stdout, result.stdout


def test_llm_eval_tests_collected_with_marker_opt_in():
    """`-m llm_eval --collect-only` must select the routing cases for collection.

    Uses --collect-only so the opt-in path is proven without ever running the
    real claude CLI (which would need the live binary and can time out).
    """
    result = _run_pytest("-m", "llm_eval", "--collect-only", "-q")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("test_skill_routing") == 7, result.stdout
