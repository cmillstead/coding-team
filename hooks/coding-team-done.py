#!/usr/bin/env python3
"""PostToolUse hook: clear coding-team active indicator when skill completes."""
import json, os, sys

ACTIVE_FILE = "/tmp/coding-team-active"

try:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")

    if tool == "Skill":
        if os.path.exists(ACTIVE_FILE):
            os.remove(ACTIVE_FILE)
except Exception:
    pass
