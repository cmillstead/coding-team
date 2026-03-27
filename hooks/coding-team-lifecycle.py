#!/usr/bin/env python3
"""Coding-team lifecycle hook: guard against recursive /coding-team invocation.

Only guards the `coding-team` entry-point skill. Sub-skills (debug, second-opinion,
harness-engineer, etc.) are designed to be invoked WITHIN the pipeline and pass through.

PreToolUse on Skill:
  - If skill is "coding-team" AND marker exists → BLOCK (recursive invocation)
  - If skill is "coding-team" AND marker absent → write marker, ALLOW
  - Any other skill → silent return

PostToolUse on Skill:
  - If skill is "coding-team" → remove marker, silent return
  - Any other skill → silent return
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import json
import time

from _lib.event import parse_event, get_tool_input
from _lib import output

ACTIVE_FILE = "/tmp/coding-team-active"


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
        # PostToolUse: clear the active marker
        try:
            if os.path.exists(ACTIVE_FILE):
                os.remove(ACTIVE_FILE)
        except OSError:
            pass
        # Clean up session phase file if it exists
        session_file = "/tmp/coding-team-session.json"
        try:
            if os.path.exists(session_file):
                os.remove(session_file)
        except OSError:
            pass
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

