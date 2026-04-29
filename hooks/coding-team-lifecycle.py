#!/usr/bin/env python3
"""Coding-team lifecycle hook: second-opinion gate via plan-file checkbox.

Only acts on the `coding-team` entry-point skill. Sub-skills (debug, second-opinion,
harness-engineer, etc.) are designed to be invoked WITHIN the pipeline and pass through.

PostToolUse on Skill (PreToolUse path is a no-op now):
  - If skill is "coding-team" → enforce second-opinion gate via active-plan checkbox
  - Any other skill → silent return

Second-opinion gate (PostToolUse):
  Reads the active plan file under $MAIN_ROOT/docs/plans/ (most recent .md whose
  frontmatter does NOT say `status: complete` and whose mtime is within the last 4h).
  Looks for a `- [ ] Second-opinion review ...` checklist line.
    - `- [x]` OR line contains `skip:` → allow
    - `- [ ]` and no `skip:`           → block with reminder
    - no matching line / no plan       → allow (back-compat / no pipeline state)
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from _lib.event import parse_event, get_tool_input
from _lib import output


SECOND_OPINION_LINE_RE = re.compile(
    r"^- \[([ xX])\] Second-opinion review.*$",
    re.MULTILINE | re.IGNORECASE,
)
PLAN_STALE_SECONDS = 4 * 3600


def find_active_plan() -> Path | None:
    """Return the most recent in-progress plan file, or None.

    A plan is "in-progress" when:
      - frontmatter does NOT contain `status: complete`, AND
      - file mtime is within the last 4 hours.
    Plans are scanned newest-first; first match wins.
    """
    try:
        raw = subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if not raw:
        return None
    # Strip trailing /.git (or worktree's literal `.git` suffix) to get repo root.
    if raw.endswith("/.git"):
        main_root = raw[: -len("/.git")]
    else:
        main_root = raw
    plans_dir = Path(main_root) / "docs" / "plans"
    if not plans_dir.exists():
        return None
    candidates = sorted(
        plans_dir.glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    now = time.time()
    for plan in candidates:
        try:
            text = plan.read_text(errors="replace")[:500]
        except OSError:
            continue
        if re.search(r"^status:\s*complete", text, re.MULTILINE | re.IGNORECASE):
            continue
        try:
            mtime = plan.stat().st_mtime
        except OSError:
            continue
        if now - mtime > PLAN_STALE_SECONDS:
            continue
        return plan
    return None


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

    plan_path = find_active_plan()
    if plan_path is None:
        # No active plan → no pipeline state to gate.
        return

    try:
        plan_text = plan_path.read_text(errors="replace")
    except OSError:
        # Plan unreadable for some reason — fail open rather than wedge the user.
        return

    match = SECOND_OPINION_LINE_RE.search(plan_text)
    if match is None:
        # Old-format plan without the checklist line — back-compat allow.
        return

    line = match.group(0)
    checkbox = match.group(1).lower()
    if checkbox == "x" or "skip:" in line.lower():
        return

    output.block(
        "Second-opinion gate: edit the active plan file's Completion Checklist to "
        "mark second-opinion done ('- [x] Second-opinion review') or add a skip "
        f"reason ('- [x] Second-opinion review (skip: <reason>)'). Active plan: {plan_path}"
    )


if __name__ == "__main__":
    main()
