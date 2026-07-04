"""Tests for paul-apply-agent-guard.py (Path B PreToolUse-on-Agent fence).

Reads a PreToolUse Agent event and blocks when the Agent prompt references a
.paul/phases/*/*-PLAN.md path with a genuine exec verb near it and that plan
lacks a valid Codex PASS. Path B LEANS BLOCK (a false negative defeats the
fence; a false positive costs one override cycle): any non-verb-adjacent-negated
exec verb near a real plan-ref triggers. A pure review/discuss dispatch has no
exec verb near the ref, so it never fires. Real temp files, no mocks.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
GUARD = HOOKS_DIR / "paul-apply-agent-guard.py"


def _load_pr():
    spec = importlib.util.spec_from_file_location(
        "paul_review", HOOKS_DIR / "_lib" / "paul_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = _load_pr()


def _run(agent_prompt, cwd, env_extra=None):
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    event = {"tool_name": "Agent", "tool_input": {"prompt": agent_prompt}}
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True, text=True, timeout=10, cwd=str(cwd), env=env,
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return result, parsed


def _make_plan(tmp_path, with_pass=False):
    sub = tmp_path / ".paul" / "phases" / "02-medium-risk-domains"
    sub.mkdir(parents=True)
    plan = sub / "02-02-PLAN.md"
    plan.write_bytes(b"plan body\n")
    if with_pass:
        review = {
            "schema_version": 1, "plan_path": str(plan),
            "plan_sha256": pr.compute_plan_hash(plan), "verdict": "PASS",
            "reviewer": "codex", "reviewer_detail": "x", "rounds": 1,
            "session": "s", "date": "2026-07-02", "recorded_by": "/second-opinion",
        }
        pr.review_path_for(plan).write_text(json.dumps(review))
    return plan


def test_execution_dispatch_no_pass_blocks(tmp_path):
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement Task 1 from {rel}. Write code and run tests."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"


def test_execution_dispatch_with_pass_allows(tmp_path):
    _make_plan(tmp_path, with_pass=True)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement Task 1 from {rel}. Write code and run tests."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is None or parsed.get("decision") != "block"


def test_pure_review_dispatch_no_exec_verb_does_not_block(tmp_path):
    """A pure review/discuss dispatch that names the plan but has NO exec verb
    near the ref must NOT block, even without a PASS. (Path B leans block, but a
    ref with no genuine exec verb near it never fires.)"""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Review {rel} and report any issues you find."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is None or parsed.get("decision") != "block"


def test_verb_adjacent_negated_implement_does_not_block(tmp_path):
    """VERB-ADJACENT NEGATION: 'Review <plan>; do NOT implement it' must NOT
    block — the negation immediately precedes the exec verb 'implement', so that
    verb is suppressed and no other exec verb is present."""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Review {rel}; do not implement it — just report gaps."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is None or parsed.get("decision") != "block"


def test_read_then_implement_blocks(tmp_path):
    """LEAN-BLOCK: 'Read <plan> and implement Task 1' must BLOCK. The word
    'Read' is review framing but does NOT immediately precede 'implement', so
    the exec verb stands. (Old broad review-suppression falsely passed this.)"""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Read {rel} and implement Task 1."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"


def test_implement_without_api_change_blocks(tmp_path):
    """LEAN-BLOCK: 'Implement <plan> without changing the public API' must BLOCK.
    'without' is a negation token but it FOLLOWS the verb (modifies 'changing',
    not 'implement'), so it does not suppress. (Old broad negation falsely
    passed this.)"""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement {rel} without changing the public API."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"


def test_implement_and_summarize_blocks(tmp_path):
    """LEAN-BLOCK: 'Implement <plan> and summarize changes' must BLOCK. 'summarize'
    is review-ish but review framing no longer suppresses; the exec verb stands."""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement {rel} and summarize the changes afterward."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"


def test_mentions_paul_apply_string_without_real_plan_ref_passes(tmp_path):
    """A prompt that mentions the /paul:apply command in prose but has no real
    .paul/phases/*-PLAN.md ref must NOT block (no plan to gate)."""
    result, parsed = _run(
        "review the /paul:apply gate design and suggest improvements", tmp_path)
    assert parsed is None or parsed.get("decision") != "block"


def test_complete_tasks_from_plan_blocks(tmp_path):
    """FALSE-NEGATIVE FIX (plural): 'complete Tasks 1-3 from <plan>' is
    execution-intent and must BLOCK when no PASS exists — the verb regex is
    plural-aware (`complete\\s+tasks?`)."""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Complete Tasks 1-3 from {rel} and commit each one."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"


def test_execute_the_plan_blocks(tmp_path):
    """'execute the plan <plan>' is execution-intent → BLOCK without a PASS."""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Execute the plan {rel} now."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"


def test_block_reason_includes_override_logging_instruction(tmp_path):
    """The Path B block message must instruct the EM to log a STATE.md row on
    override (override-logging is instruction-strength, not silent)."""
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement Task 1 from {rel}."
    result, parsed = _run(prompt, tmp_path)
    assert parsed is not None and parsed["decision"] == "block"
    reason = parsed["reason"]
    assert "override-plan-review" in reason
    assert "STATE.md" in reason and "Decisions" in reason


def test_prompt_without_plan_ref_passes(tmp_path):
    result, parsed = _run("Refactor the auth module and add tests.", tmp_path)
    assert parsed is None or parsed.get("decision") != "block"


def test_override_phrase_allows(tmp_path):
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement Task 1 from {rel}. override-plan-review em-approved"
    result, parsed = _run(prompt, tmp_path)
    assert parsed is None or parsed.get("decision") != "block"


def test_env_disable_allows(tmp_path):
    _make_plan(tmp_path, with_pass=False)
    rel = ".paul/phases/02-medium-risk-domains/02-02-PLAN.md"
    prompt = f"Implement Task 1 from {rel}."
    result, parsed = _run(prompt, tmp_path, env_extra={"PAUL_APPLY_GATE_DISABLE": "1"})
    assert parsed is None or parsed.get("decision") != "block"


def test_non_agent_event_passes(tmp_path):
    event = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}
    result = subprocess.run(
        [sys.executable, str(GUARD)], input=json.dumps(event),
        capture_output=True, text=True, timeout=10, cwd=str(tmp_path),
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""
