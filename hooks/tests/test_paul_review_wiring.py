"""Regression guard for the /second-opinion -> paul_review_record.py wiring.

The recorder script (hooks/_lib/paul_review_record.py) exists, works, and is
fully tested in isolation (test_paul_review.py), but nothing invoked it until
skills/second-opinion/{reference.md,SKILL.md} were wired to call it on a PAUL
plan PASS. This test reads the actual instruction files (no mocks) and asserts
the wiring text is present, so the dark-feature regression cannot silently
return.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REFERENCE_MD = REPO_ROOT / "skills" / "second-opinion" / "reference.md"
SKILL_MD = REPO_ROOT / "skills" / "second-opinion" / "SKILL.md"


def test_reference_md_documents_the_recorder_invocation():
    # Arrange
    text = REFERENCE_MD.read_text(encoding="utf-8")

    # Act / Assert
    assert "paul_review_record.py" in text
    assert "--reviewer codex" in text


def test_reference_md_documents_the_pass_only_trigger():
    # Arrange
    text = REFERENCE_MD.read_text(encoding="utf-8")

    # Act / Assert
    assert "Record PAUL plan-review PASS" in text
    assert "-PLAN.md" in text


def test_reference_md_requires_re_review_after_post_approval_plan_edits():
    # Arrange: the recorder must never hash bytes Codex didn't actually
    # review — an APPROVED verdict with post-approval fixes must trigger a
    # fresh re-dispatch before the recorder runs (freshness guarantee).
    text = REFERENCE_MD.read_text(encoding="utf-8")

    # Act
    record_section_start = text.index("### Record PAUL plan-review PASS")
    record_section = text[record_section_start:]

    # Assert
    assert "since that approving review" in record_section
    assert "re-dispatch Codex" in record_section


def test_skill_md_points_reviewers_at_the_paul_record_step():
    # Arrange
    text = SKILL_MD.read_text(encoding="utf-8")

    # Act / Assert
    assert "PAUL plan" in text
    assert "Record PAUL plan-review PASS" in text


def test_skill_md_checklist_rule_stays_unconditional():
    # Arrange: the Completion Checklist instruction must not be scoped behind
    # the PAUL "If ..." clause — every review (diff, non-PAUL plan, challenge)
    # still needs the checkbox updated for the coding-team lifecycle gate.
    text = SKILL_MD.read_text(encoding="utf-8")

    # Act
    checklist_idx = text.index("update the active plan file's Completion Checklist")
    paul_clause_idx = text.index("if the review target was a PAUL plan")

    # Assert: unconditional checklist instruction precedes the separate,
    # independent PAUL recorder clause — not the other way around.
    assert checklist_idx < paul_clause_idx


def test_skill_md_stays_within_the_200_physical_line_cap():
    # Arrange
    lines = SKILL_MD.read_text(encoding="utf-8").splitlines()

    # Act
    line_count = len(lines)

    # Assert
    assert line_count <= 200
