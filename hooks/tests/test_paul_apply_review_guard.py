"""Tests for paul-apply-review-guard.py (Path A UserPromptSubmit fence).

The hook reads a UserPromptSubmit event {"prompt": "..."} on stdin and emits
{"decision":"block","reason":...} on stdout (exit 0) when a /paul:apply for a
plan without a valid Codex PASS is detected. Real temp files, no mocks.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")
GUARD = HOOKS_DIR / "paul-apply-review-guard.py"


def _load_pr():
    spec = importlib.util.spec_from_file_location(
        "paul_review", HOOKS_DIR / "_lib" / "paul_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = _load_pr()


def _run(prompt, cwd, env_extra=None):
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"prompt": prompt}),
        capture_output=True, text=True, timeout=10, cwd=str(cwd), env=env,
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return result, parsed


def _plan_with_pass(tmp_path):
    plan = tmp_path / "02-02-PLAN.md"
    plan.write_bytes(b"plan body\n")
    review = {
        "schema_version": 1, "plan_path": str(plan),
        "plan_sha256": pr.compute_plan_hash(plan), "verdict": "PASS",
        "reviewer": "codex", "reviewer_detail": "codex exec", "rounds": 1,
        "session": "s", "date": "2026-07-02", "recorded_by": "/second-opinion",
    }
    pr.review_path_for(plan).write_text(json.dumps(review))
    return plan


def test_non_apply_prompt_passes_silently(tmp_path):
    result, parsed = _run("please help me with the code", tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""  # silent pass


def test_apply_no_pass_blocks(tmp_path):
    plan = tmp_path / "02-02-PLAN.md"
    plan.write_bytes(b"plan body\n")  # no .review.json
    result, parsed = _run(f"/paul:apply {plan}", tmp_path)
    assert result.returncode == 0
    assert parsed is not None
    assert parsed["decision"] == "block"
    assert "MISSING" in parsed["reason"] or "/second-opinion" in parsed["reason"]


def test_apply_valid_pass_allows(tmp_path):
    plan = _plan_with_pass(tmp_path)
    result, parsed = _run(f"/paul:apply {plan}", tmp_path)
    assert result.returncode == 0
    # allow == no block decision
    assert parsed is None or parsed.get("decision") != "block"


def test_apply_stale_blocks(tmp_path):
    plan = _plan_with_pass(tmp_path)
    plan.write_bytes(b"plan body EDITED\n")  # invalidate hash
    result, parsed = _run(f"/paul:apply {plan}", tmp_path)
    assert result.returncode == 0
    assert parsed is not None and parsed["decision"] == "block"
    assert "STALE" in parsed["reason"] or "edited" in parsed["reason"].lower()


def test_apply_no_arg_passes(tmp_path):
    # command's own validate_plan handles "which plan?" — hook must not block
    result, parsed = _run("/paul:apply", tmp_path)
    assert result.returncode == 0
    assert parsed is None or parsed.get("decision") != "block"


def test_override_phrase_allows(tmp_path):
    plan = tmp_path / "02-02-PLAN.md"
    plan.write_bytes(b"plan body\n")  # no PASS, would normally block
    result, parsed = _run(
        f"/paul:apply {plan} override-plan-review not-ready-yet", tmp_path)
    assert result.returncode == 0
    assert parsed is None or parsed.get("decision") != "block"


def test_env_disable_passes(tmp_path):
    plan = tmp_path / "02-02-PLAN.md"
    plan.write_bytes(b"plan body\n")  # no PASS
    result, parsed = _run(
        f"/paul:apply {plan}", tmp_path, env_extra={"PAUL_APPLY_GATE_DISABLE": "1"})
    assert result.returncode == 0
    assert parsed is None or parsed.get("decision") != "block"


def test_relative_plan_arg_resolves_against_cwd(tmp_path):
    sub = tmp_path / ".paul" / "phases" / "02"
    sub.mkdir(parents=True)
    plan = sub / "02-02-PLAN.md"
    plan.write_bytes(b"plan body\n")  # no PASS
    rel = ".paul/phases/02/02-02-PLAN.md"
    result, parsed = _run(f"/paul:apply {rel}", tmp_path)
    assert result.returncode == 0
    assert parsed is not None and parsed["decision"] == "block"
