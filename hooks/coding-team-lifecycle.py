#!/usr/bin/env python3
"""Coding-team lifecycle hook: activate on entry, guard against recursion, deactivate on exit.

Consolidates coding-team-active.py, recursive-invocation-guard.py, and coding-team-done.py.

PreToolUse on Skill:
  - If coding-team skill AND marker exists → BLOCK (recursive invocation)
  - If coding-team skill AND marker absent → write marker, ALLOW
  - Non-coding-team skill → silent return

PostToolUse on Skill:
  - If coding-team skill → remove marker, silent return
  - Non-coding-team skill → silent return
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import json
import time
from pathlib import Path

from _lib.event import parse_event, get_tool_input
from _lib import output

ACTIVE_FILE = "/tmp/coding-team-active"
SKILLS_DIR = Path.home() / ".claude" / "skills" / "coding-team" / "skills"

FALLBACK_SKILLS = {
    "coding-team", "debug", "verify", "tdd", "review-feedback", "worktree",
    "parallel-fix", "prompt-craft", "second-opinion", "scope-lock",
    "scope-unlock", "release", "retrospective", "doc-sync",
    "harness-engineer",
}


def get_skill_names():
    """Discover skill names from the skills directory. Falls back to static set."""
    try:
        if SKILLS_DIR.is_dir():
            names = set()
            for item in SKILLS_DIR.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    names.add(item.name)
            if names:
                names.add("coding-team")
                return names
    except OSError:
        pass
    return FALLBACK_SKILLS


def main():
    event = parse_event()
    if not event:
        return

    tool = event.get("tool_name", "")
    if tool != "Skill":
        return

    tool_input = get_tool_input(event)
    skill_name = tool_input.get("skill_name", "") or tool_input.get("skill", "")

    skill_names = get_skill_names()
    if skill_name not in skill_names:
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

