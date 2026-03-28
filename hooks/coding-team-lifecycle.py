#!/usr/bin/env python3
"""Coding-team lifecycle hook: recursion guard + second-opinion gate.

Only guards the `coding-team` entry-point skill. Sub-skills (debug, second-opinion,
harness-engineer, etc.) are designed to be invoked WITHIN the pipeline and pass through.

PreToolUse on Skill:
  - If skill is "coding-team" AND marker exists → BLOCK (recursive invocation)
  - If skill is "coding-team" AND marker absent → write marker, ALLOW
  - Any other skill → silent return

PostToolUse on Skill:
  - If skill is "coding-team" → check second-opinion gate, then clean up markers
  - Any other skill → silent return

Second-opinion gate (PostToolUse):
  Blocks pipeline completion unless one of these markers exists:
  - /tmp/second-opinion-completed  (user ran codex)
  - /tmp/second-opinion-declined   (user explicitly skipped)
  Fail-closed: if neither exists, block and remind the orchestrator to offer.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import json
import time

from _lib.event import parse_event, get_tool_input
from _lib import output

ACTIVE_FILE = "/tmp/coding-team-active"
SO_COMPLETED = "/tmp/second-opinion-completed"
SO_DECLINED = "/tmp/second-opinion-declined"


def _cleanup_markers():
    """Remove all session markers. Called after gate passes."""
    for path in [ACTIVE_FILE, "/tmp/coding-team-session.json", SO_COMPLETED, SO_DECLINED]:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _check_second_opinion_gate() -> bool:
    """Return True if gate passes (marker exists), False if blocked.

    Fail-closed: if neither marker exists, the gate blocks.
    """
    return os.path.exists(SO_COMPLETED) or os.path.exists(SO_DECLINED)


def main():
    event = parse_event()
    if not event:
        return

    tool = event.get("tool_name", "")
    if tool != "Skill":
        return

    tool_input = get_tool_input(event)
    skill_name = tool_input.get("skill_name", "") or tool_input.get("skill", "")

    # Only guard the pipeline entry point — sub-skills are safe to invoke within the pipeline
    if skill_name != "coding-team":
        return

    is_post = "tool_result" in event

    if is_post:
        # PostToolUse: check second-opinion gate before allowing completion
        if not _check_second_opinion_gate():
            output.block(
                "Second-opinion gate: you must offer `/second-opinion review` or "
                "`/second-opinion challenge` before completing the pipeline. "
                "If the user declines, write the marker: "
                "touch /tmp/second-opinion-declined"
            )
            return
        # Gate passed — clean up all markers
        _cleanup_markers()
        return

    # PreToolUse: check for recursion, then activate
    if os.path.exists(ACTIVE_FILE):
        output.block(
            "You are already inside the coding-team pipeline. "
            "Do not invoke /coding-team recursively. "
            "Complete the current task within the existing pipeline."
        )
        return

    with open(ACTIVE_FILE, "w") as f:
        f.write(str(time.time()))

    # Create session phase file for execution-phase hooks
    session_file = "/tmp/coding-team-session.json"
    try:
        with open(session_file, "w") as sf:
            json.dump({"phase": "active", "ts": time.time()}, sf)
    except OSError:
        pass


if __name__ == "__main__":
    main()

