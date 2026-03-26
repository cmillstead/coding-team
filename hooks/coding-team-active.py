#!/usr/bin/env python3
"""PreToolUse hook: mark coding-team as active when a coding-team skill is invoked."""
import json
import sys
import time
from pathlib import Path

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


try:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool == "Skill":
        skill_name = tool_input.get("skill_name", tool_input.get("skill", ""))
        skill_names = get_skill_names()
        if skill_name in skill_names:
            with open(ACTIVE_FILE, "w") as f:
                f.write(str(time.time()))
except (json.JSONDecodeError, ValueError, KeyError):
    pass

print(json.dumps({"decision": "allow"}))
