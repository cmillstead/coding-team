"""Tests for coding-team-lifecycle.py hook.

The hook derives state from the active plan file under
$MAIN_ROOT/docs/plans/*.md. The "active" plan is the unique plan whose
YAML frontmatter declares `status: in-progress`. We construct a fake
git repo per-test under `tmp_path` and set CWD to it; the hook calls
`git rev-parse --git-common-dir` which then points into the temp repo.

Each test runs the hook in a subprocess with a fresh CWD (the tmp_path repo)
so we never touch real plan directories.
"""

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest


HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
HOOK_PATH = HOOKS_DIR / "coding-team-lifecycle.py"

ACTIVE_FRONTMATTER = "---\nstatus: in-progress\n---\n\n"


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


def _active_plan(checklist_state: str = "[ ]", trailing: str = "") -> str:
    """Build a canonical in-progress plan body with a Completion Checklist."""
    return (
        ACTIVE_FRONTMATTER
        + "# Plan\n\n## Completion Checklist\n"
        + f"- {checklist_state} Second-opinion review{trailing}\n"
    )


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
# Plan-state behavior — basic gate
# ---------------------------------------------------------------------------


def test_no_plan_found_allows(repo: Path):
    """No docs/plans dir -> silent allow (no pipeline state to gate)."""
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_unchecked_blocks(repo: Path):
    """In-progress plan with `- [ ] Second-opinion review` blocks completion."""
    _write_plan(repo, "plan.md", _active_plan("[ ]"))
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None, f"expected JSON output, got {result.stdout!r}"
    assert parsed.get("decision") == "block"
    assert "second-opinion" in parsed.get("reason", "").lower()


def test_checked_allows(repo: Path):
    """In-progress plan with `- [x] Second-opinion review` allows."""
    _write_plan(repo, "plan.md", _active_plan("[x]"))
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block"


def test_skip_reason_allows(repo: Path):
    """`- [x] Second-opinion review (skip: <reason>)` allows."""
    _write_plan(repo, "plan.md", _active_plan("[x]", " (skip: vendor lib only)"))
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block"


def test_skip_reason_overrides_unchecked(repo: Path):
    """Even an unchecked line allows if it contains `skip:`."""
    _write_plan(repo, "plan.md", _active_plan("[ ]", " (skip: trivial doc edit)"))
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block"


def test_no_checklist_line_allows(repo: Path):
    """In-progress plan without the checklist section allows (back-compat)."""
    _write_plan(
        repo,
        "old-format.md",
        ACTIVE_FRONTMATTER + "# Plan\n\nSome content but no Completion Checklist section.\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Plan-state behavior — frontmatter-driven activation (new contract)
# ---------------------------------------------------------------------------


def test_status_in_progress_required(repo: Path):
    """Plan without `status: in-progress` frontmatter -> no gate (no block)."""
    # Plan is `status: planned`, not in-progress -> no gate
    _write_plan(
        repo,
        "planned.md",
        "---\nstatus: planned\n---\n\n# Plan\n\n## Completion Checklist\n"
        "- [ ] Second-opinion review\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"expected silent allow for status: planned plan, got {result.stdout!r}"
    )


def test_multiple_in_progress_blocks(repo: Path):
    """Two plans with `status: in-progress` -> AmbiguousActivePlanError -> block."""
    _write_plan(repo, "plan-a.md", _active_plan("[x]"))
    _write_plan(repo, "plan-b.md", _active_plan("[x]"))
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None, f"expected JSON output, got {result.stdout!r}"
    assert parsed.get("decision") == "block"
    reason = parsed.get("reason", "").lower()
    assert "cannot determine active plan state" in reason
    assert "multiple plans" in reason or "in-progress" in reason


def test_unreadable_plan_blocks(repo: Path):
    """chmod 000 on an in-progress plan -> fail closed -> block."""
    plan = _write_plan(repo, "locked.md", _active_plan("[x]"))
    # Strip all permissions
    plan.chmod(0)
    try:
        result = _run_hook(_post_event(), cwd=repo)
    finally:
        plan.chmod(stat.S_IRUSR | stat.S_IWUSR)  # restore so tmp cleanup works
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None, f"expected JSON output, got {result.stdout!r}"
    assert parsed.get("decision") == "block"
    reason = parsed.get("reason", "").lower()
    assert "cannot determine active plan state" in reason
    assert "unreadable" in reason


def test_body_status_complete_ignored(repo: Path):
    """A `status: complete` line in the BODY (not frontmatter) is ignored."""
    body = (
        ACTIVE_FRONTMATTER
        + "# Plan\n\n"
        + "Note: previous plan was status: complete. This one is in-progress.\n\n"
        + "## Completion Checklist\n- [ ] Second-opinion review\n"
    )
    _write_plan(repo, "plan.md", body)
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None and parsed.get("decision") == "block", (
        f"expected block: body 'status: complete' must be ignored, got {result.stdout!r}"
    )


def test_no_frontmatter_no_gate(repo: Path):
    """Plan without leading `---` frontmatter -> no gate (no block)."""
    _write_plan(
        repo,
        "noframe.md",
        "# Plan\n\n## Completion Checklist\n- [ ] Second-opinion review\n",
    )
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        f"expected silent allow for no-frontmatter plan, got {result.stdout!r}"
    )


def test_bom_frontmatter_parsed(repo: Path):
    """UTF-8 BOM + frontmatter -> parsed correctly, gate fires."""
    body = "﻿" + _active_plan("[ ]")
    _write_plan(repo, "bom.md", body)
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None and parsed.get("decision") == "block", (
        f"expected block on BOM-prefixed in-progress plan, got {result.stdout!r}"
    )


def test_checklist_outside_section_ignored(repo: Path):
    """`- [x] Second-opinion review` outside `## Completion Checklist` doesn't satisfy gate."""
    body = (
        ACTIVE_FRONTMATTER
        + "# Plan\n\n"
        + "## Notes\n- [x] Second-opinion review (this is a doc example)\n\n"
        + "## Completion Checklist\n- [ ] Second-opinion review\n"
    )
    _write_plan(repo, "plan.md", body)
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None and parsed.get("decision") == "block", (
        f"expected block — only Completion Checklist counts, got {result.stdout!r}"
    )


def test_checklist_format_variations(repo: Path):
    """Tolerates `- [X]`, extra whitespace, tab indent."""
    body = (
        ACTIVE_FRONTMATTER
        + "# Plan\n\n## Completion Checklist\n"
        + "\t-  [X]  Second-opinion review\n"
    )
    _write_plan(repo, "plan.md", body)
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    if parsed is not None:
        assert parsed.get("decision") != "block", (
            f"expected allow on `- [X]` with tab indent, got {result.stdout!r}"
        )


def test_star_bullet_does_not_match(repo: Path):
    """`* [x] Second-opinion review` does NOT match (canonical is `-`)."""
    body = (
        ACTIVE_FRONTMATTER
        + "# Plan\n\n## Completion Checklist\n"
        + "* [x] Second-opinion review\n"
    )
    _write_plan(repo, "plan.md", body)
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    # No `-` bullet match found -> falls through as no checklist line -> allow.
    if parsed is not None:
        assert parsed.get("decision") != "block", (
            f"expected silent allow (no canonical bullet match), got {result.stdout!r}"
        )


def test_long_session_no_expiry(repo: Path):
    """Plan with mtime 7 days ago is still active when status is in-progress."""
    week_old = time.time() - (7 * 24 * 3600)
    _write_plan(repo, "long.md", _active_plan("[ ]"), mtime=week_old)
    result = _run_hook(_post_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    parsed = _parse_or_none(result.stdout)
    assert parsed is not None and parsed.get("decision") == "block", (
        f"expected block on week-old in-progress plan (no mtime expiry), got {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Multi-plan resolution — frontmatter, not mtime
# ---------------------------------------------------------------------------


def test_complete_frontmatter_skipped(repo: Path):
    """Plan with `status: complete` frontmatter is ignored.

    Older plan is in-progress, newer plan is complete -> in-progress one wins.
    """
    older_mtime = time.time() - 60   # 1 min ago
    newer_mtime = time.time() - 30   # 30 sec ago

    _write_plan(repo, "older.md", _active_plan("[ ]"), mtime=older_mtime)
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
        f"expected block on in-progress plan despite complete sibling, got {result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Surface guards
# ---------------------------------------------------------------------------


def test_pretooluse_noop(repo: Path):
    """PreToolUse event (no tool_result) -> no output, no exception."""
    _write_plan(repo, "plan.md", _active_plan("[ ]"))
    result = _run_hook(_pre_event(), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""


def test_non_coding_team_skill_skips(repo: Path):
    """skill_name is `debug` -> return early, no work, silent allow."""
    _write_plan(repo, "plan.md", _active_plan("[ ]"))
    result = _run_hook(_post_event(skill="debug"), cwd=repo)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""
