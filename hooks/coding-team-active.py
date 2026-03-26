#!/usr/bin/env python3
"""PreToolUse hook: mark coding-team as active when a coding-team skill is invoked."""
import json, sys, time

ACTIVE_FILE = "/tmp/coding-team-active"
SKILL_NAMES = {
    "coding-team", "debug", "verify", "tdd", "review-feedback", "worktree",
    "parallel-fix", "prompt-craft", "second-opinion", "scope-lock",
    "scope-unlock", "release", "retrospective", "doc-sync",
}

try:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool == "Skill":
        skill_name = tool_input.get("skill_name", "")
        if skill_name in SKILL_NAMES:
            with open(ACTIVE_FILE, "w") as f:
                f.write(str(time.time()))
except Exception:
    pass

# Always allow — this hook only sets the indicator
print(json.dumps({"decision": "allow"}))
