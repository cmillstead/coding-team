#!/usr/bin/env python3
"""Coding-team lifecycle hook: second-opinion gate via plan-file checkbox.

Only acts on the `coding-team` entry-point skill. Sub-skills (debug, second-opinion,
harness-engineer, etc.) are designed to be invoked WITHIN the pipeline and pass through.

PostToolUse on Skill (PreToolUse path is a no-op now):
  - If skill is "coding-team" -> enforce second-opinion gate via active-plan checkbox
  - Any other skill -> silent return

Second-opinion gate (PostToolUse):
  Reads the active plan file under $MAIN_ROOT/docs/plans/ — the unique plan whose
  YAML frontmatter declares `status: in-progress`. Within the
  `## Completion Checklist` section, looks for `- [ ] Second-opinion review ...`:
    - `- [x]` (or `- [X]`) -> allow
    - line contains `skip:` -> allow (gate-satisfied with explicit skip)
    - `- [ ]` and no `skip:` -> block with reminder
    - no checklist section / no matching line / no plan -> allow (back-compat)

  If multiple plans claim `status: in-progress` or a plan is unreadable, the
  helper raises AmbiguousActivePlanError; we block with a remediation message.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

from _lib.event import parse_event, get_tool_input
from _lib import output
from _lib.active_plan import find_active_plan, AmbiguousActivePlanError


_COMPLETION_SECTION_RE = re.compile(
    r"^##\s+Completion\s+Checklist\s*\n(.*?)(?=\n##\s|\Z)",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)

_CHECKLIST_LINE_RE = re.compile(
    r"^\s*-\s*\[([ xX])\]\s+Second-opinion\s+review\b(.*)$",
    re.MULTILINE,
)


def _read_second_opinion_state(plan_text: str) -> str | None:
    """Return 'checked', 'unchecked', or None if no checklist line found.

    Scopes the search to the first `## Completion Checklist` section.
    Tolerates leading whitespace and varied whitespace between `[x]` and
    the label. Does not match `*` bullets — must be `-` to match the
    canonical template.
    """
    section_match = _COMPLETION_SECTION_RE.search(plan_text)
    if not section_match:
        return None  # back-compat: old plans without the section -> allow
    section = section_match.group(1)
    line_match = _CHECKLIST_LINE_RE.search(section)
    if not line_match:
        return None
    box, trailing = line_match.group(1), line_match.group(2)
    if box.lower() == "x":
        return "checked"
    if "skip:" in trailing.lower():
        return "checked"  # explicit skip with reason counts as gate-satisfied
    return "unchecked"


def main() -> None:
    event = parse_event()
    if not event:
        return

    if event.get("tool_name", "") != "Skill":
        return

    tool_input = get_tool_input(event)
    skill_name = tool_input.get("skill_name", "") or tool_input.get("skill", "")
    if skill_name != "coding-team":
        return

    is_post = "tool_result" in event
    if not is_post:
        # PreToolUse path is now a no-op — recursion guard removed; re-entry resumes
        # via session-resume.md based on durable plan-file state.
        return

    try:
        plan_path = find_active_plan()
    except AmbiguousActivePlanError as exc:
        output.block(
            f"BLOCKED: cannot determine active plan state — {exc}. "
            f"Either fix the plan file's readability or remove its "
            f"`status: in-progress` frontmatter and try again."
        )
        return

    if plan_path is None:
        # No active plan -> no pipeline state to gate.
        return

    try:
        plan_text = plan_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # Race: plan disappeared/became unreadable between find_active_plan()
        # and this read. Fail closed for safety.
        output.block(
            f"BLOCKED: cannot determine active plan state — unreadable plan "
            f"{plan_path}: {exc}. Either fix the plan file's readability or "
            f"remove its `status: in-progress` frontmatter and try again."
        )
        return

    state = _read_second_opinion_state(plan_text)
    if state is None or state == "checked":
        return

    # state == "unchecked"
    output.block(
        "Second-opinion gate: edit the active plan file's Completion Checklist to "
        "mark second-opinion done ('- [x] Second-opinion review') or add a skip "
        f"reason ('- [x] Second-opinion review (skip: <reason>)'). Active plan: {plan_path}"
    )


if __name__ == "__main__":
    main()
