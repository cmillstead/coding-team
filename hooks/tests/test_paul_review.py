"""Tests for _lib/paul_review.py — shared PAUL plan-review detection primitive.

Real temp files, no mocks (rules/test-files.md).
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")


def _load():
    spec = importlib.util.spec_from_file_location(
        "paul_review", HOOKS_DIR / "_lib" / "paul_review.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = _load()


# --- compute_plan_hash canonicalization ---

def test_hash_stable_across_crlf(tmp_path):
    lf = tmp_path / "a-PLAN.md"
    crlf = tmp_path / "b-PLAN.md"
    lf.write_bytes(b"line1\nline2\n")
    crlf.write_bytes(b"line1\r\nline2\r\n")
    assert pr.compute_plan_hash(lf) == pr.compute_plan_hash(crlf)


def test_hash_stable_across_trailing_newline(tmp_path):
    with_nl = tmp_path / "a-PLAN.md"
    without_nl = tmp_path / "b-PLAN.md"
    with_nl.write_bytes(b"body\n")
    without_nl.write_bytes(b"body")
    assert pr.compute_plan_hash(with_nl) == pr.compute_plan_hash(without_nl)


def test_hash_changes_on_one_char_edit(tmp_path):
    p1 = tmp_path / "a-PLAN.md"
    p2 = tmp_path / "b-PLAN.md"
    p1.write_bytes(b"the plan body\n")
    p2.write_bytes(b"the plan bodyX\n")
    assert pr.compute_plan_hash(p1) != pr.compute_plan_hash(p2)


def test_hash_lone_cr_normalized(tmp_path):
    lf = tmp_path / "a-PLAN.md"
    cr = tmp_path / "b-PLAN.md"
    lf.write_bytes(b"x\ny\n")
    cr.write_bytes(b"x\ry")
    assert pr.compute_plan_hash(lf) == pr.compute_plan_hash(cr)


# --- review_path_for ---

def test_review_path_for_sibling(tmp_path):
    plan = tmp_path / "02-02-PLAN.md"
    assert pr.review_path_for(plan) == tmp_path / "02-02-PLAN.review.json"


# --- APPLY_RE ---

def test_apply_re_matches_with_arg():
    m = pr.APPLY_RE.match("/paul:apply .paul/phases/02/02-02-PLAN.md")
    assert m is not None
    assert m.group(1) == ".paul/phases/02/02-02-PLAN.md"


def test_apply_re_matches_no_arg():
    m = pr.APPLY_RE.match("/paul:apply")
    assert m is not None
    assert m.group(1) is None


def test_apply_re_case_insensitive_and_leading_ws():
    assert pr.APPLY_RE.match("   /PAUL:APPLY foo") is not None


def test_apply_re_no_match_on_other_prompt():
    assert pr.APPLY_RE.match("please run the plan") is None


# --- validate_review ---

def _write_plan(tmp_path, body=b"plan body\n"):
    plan = tmp_path / "02-02-PLAN.md"
    plan.write_bytes(body)
    return plan


def _write_review(plan, **overrides):
    data = {
        "schema_version": 1,
        "plan_path": str(plan),
        "plan_sha256": pr.compute_plan_hash(plan),
        "verdict": "PASS",
        "reviewer": "codex",
        "reviewer_detail": "codex exec, 1 round",
        "rounds": 1,
        "session": "sess-1",
        "date": "2026-07-02",
        "recorded_by": "/second-opinion",
    }
    data.update(overrides)
    pr.review_path_for(plan).write_text(json.dumps(data))


def test_validate_ok(tmp_path):
    plan = _write_plan(tmp_path)
    _write_review(plan)
    ok, status, _ = pr.validate_review(plan)
    assert ok is True and status == "OK"


def test_validate_missing(tmp_path):
    plan = _write_plan(tmp_path)
    ok, status, _ = pr.validate_review(plan)
    assert ok is False and status == "MISSING"


def test_validate_malformed(tmp_path):
    plan = _write_plan(tmp_path)
    pr.review_path_for(plan).write_text("{not json")
    ok, status, _ = pr.validate_review(plan)
    assert ok is False and status == "MALFORMED"


def test_validate_not_pass(tmp_path):
    plan = _write_plan(tmp_path)
    _write_review(plan, verdict="REVISE")
    ok, status, _ = pr.validate_review(plan)
    assert ok is False and status == "NOT_PASS"


def test_validate_wrong_reviewer(tmp_path):
    plan = _write_plan(tmp_path)
    _write_review(plan, reviewer="claude")
    ok, status, _ = pr.validate_review(plan)
    assert ok is False and status == "WRONG_REVIEWER"


def test_validate_stale_after_edit(tmp_path):
    plan = _write_plan(tmp_path)
    _write_review(plan)
    plan.write_bytes(b"plan body EDITED\n")  # hash now differs
    ok, status, _ = pr.validate_review(plan)
    assert ok is False and status == "STALE"


def test_validate_plan_unreadable(tmp_path):
    missing = tmp_path / "gone-PLAN.md"
    ok, status, _ = pr.validate_review(missing)
    assert ok is False and status == "PLAN_UNREADABLE"


def test_validate_detail_is_actionable(tmp_path):
    plan = _write_plan(tmp_path)
    ok, status, detail = pr.validate_review(plan)
    assert "/second-opinion review" in detail  # error message is an instruction
