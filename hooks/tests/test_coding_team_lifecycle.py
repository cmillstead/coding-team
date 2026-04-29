"""Tests for coding-team-lifecycle.py hook.

The hook now derives state from the active plan file under
$MAIN_ROOT/docs/plans/*.md. We construct a fake git repo per-test under
`tmp_path` and set CWD to it; the hook calls `git rev-parse --git-common-dir`
which then points into the temp repo.

Each test runs the hook in a subprocess with a fresh CWD (the tmp_path repo)
so we never touch real /tmp markers or real plan directories.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
HOOK_PATH = HOOKS_DIR / "coding-team-lifecycle.py"


def _init_repo(repo_root: Path) -> None:
    """Initialize a minimal git repo at repo_root."""
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo_root)],
        check=True,
        capture_output=True,
    )


def _run_hook(event: dict, cwd: Path) -> subprocess.CompletedProcess:
    """Run the lifecycle hook with given event and cwd."""
    return subprocess.run(
        ["python3", str(HOOK_PATH)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(cwd),
    )


def _post_event(skill: str = "coding-team") -> dict:
    """PostToolUse event for a Skill invocation."""
    return {
        "tool_name": "Skill",
        "tool_input": {"skill": skill},
        "tool_result": "done",
    }


def _pre_event(skill: str = "coding-team") -> dict:
    """PreToolUse event (no tool_result key)."""
    return {
        "tool_name": "Skill",
        "tool_input": {"skill": skill},
    }


def _write_plan(repo_root: Path, name: str, body: str, mtime: float | None = None) -> Path:
    """Create a plan file under docs/plans/ with optional mtime override."""
    plans_dir = repo_root / "docs" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan = plans_dir / name
    plan.write_text(body)
    if mtime is not None:
        os.utime(plan, (mtime, mtime))
    return plan


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Fresh git repo under tmp_path; tests cd into this for the subprocess."""
    _init_repo(tmp_path)
    return tmp_path


def _parse_or_none(stdout: str) -> dict | None:
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Plan-state behavior
# ---------------------------------------------------------------------------


def test_no_plan_found_allows(repo: Path):
    """No docs/plans dir → silent allow (no pipeline state to gate)."""
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_unchecked_blocks(repo: Path):
    """Plan with `- [ ] Second-opinion review` blocks pipeline completion."""
    _write_plan(
        repo,
        "plan.md",
        "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None, f"expected JSON output, got {result.stdout!r}"
    assert parsed.get("decision") == "block"
    assert "second-opinion" in parsed.get("reason", "").lower()


def test_checked_allows(repo: Path):
    """Plan with `- [x] Second-opinion review` allows."""
    _write_plan(
        repo,
        "plan.md",
        "# Plan\n\n## Completion Checklist\n- [x] Second-opinion review\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block"


def test_skip_reason_allows(repo: Path):
    """`- [x] Second-opinion review (skip: <reason>)` allows."""
    _write_plan(
        repo,
        "plan.md",
        "# Plan\n\n## Completion Checklist\n"
        "- [x] Second-opinion review (skip: vendor lib only)\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block"


def test_skip_reason_overrides_unchecked(repo: Path):
    """Even an unchecked line allows if it contains `skip:`."""
    _write_plan(
        repo,
        "plan.md",
        "# Plan\n\n## Completion Checklist\n"
        "- [ ] Second-opinion review (skip: trivial doc edit)\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block"


def test_complete_frontmatter_skipped(repo: Path):
    """A plan marked `status: complete` is ignored; falls back to next-newest plan.

    Newest plan is complete → skip. Older plan unchecked → block.
    """
    older_mtime = time.time() - 60  # 1 minute ago
    newer_mtime = time.time() - 30  # 30 seconds ago — more recent

    # Older plan (created first / older mtime): unchecked
    _write_plan(
        repo,
        "older.md",
        "# Older plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
        mtime=older_mtime,
    )
    # Newer plan: marked complete in frontmatter — should be skipped
    _write_plan(
        repo,
        "newer.md",
        "---\nstatus: complete\n---\n\n# Newer plan\n\n## Completion Checklist\n"
        "- [ ] Second-opinion review\n",
        mtime=newer_mtime,
    )

    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None and parsed.get("decision") == "block", (
        f"expected fallback to older plan to block, got {result.stdout!r}"
    )


def test_stale_plan_allows(repo: Path):
    """Plan older than 4h is treated as no-plan → allow."""
    stale_mtime = time.time() - (5 * 3600)  # 5 hours ago
    _write_plan(
        repo,
        "stale.md",
        "# Stale plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
        mtime=stale_mtime,
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_no_checklist_line_allows(repo: Path):
    """Old-format plan without the line allows (back-compat)."""
    _write_plan(
        repo,
        "old-format.md",
        "# Plan\n\nSome content but no Completion Checklist section.\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Surface guards
# ---------------------------------------------------------------------------


def test_pretooluse_noop(repo: Path):
    """PreToolUse event (no tool_result) → no output, no exception."""
    # Even with a blocking plan in place, PreToolUse must not gate.
    _write_plan(
        repo,
        "plan.md",
        "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
    )
    result = _run_hook(_pre_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""


def test_non_coding_team_skill_skips(repo: Path):
    """skill_name is `debug` → return early, no work, silent allow."""
    # Even with a blocking plan in place, sub-skill events must pass through.
    _write_plan(
        repo,
        "plan.md",
        "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
    )
    result = _run_hook(_post_event(skill="debug"), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
