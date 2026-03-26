#!/usr/bin/env python3
"""PostToolUse hook: clear coding-team active indicator when a coding-team skill completes.

Only clears for coding-team skills — mirrors the set logic in coding-team-active.py.
If a non-coding-team skill runs during a coding-team session (e.g., nested /prompt-craft),
the active marker is preserved.
"""
import json
import os
import sys
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


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"decision": "allow"}))
        return

    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool == "Skill":
        skill_name = tool_input.get("skill_name", tool_input.get("skill", ""))
        skill_names = get_skill_names()
        if skill_name in skill_names:
            try:
                if os.path.exists(ACTIVE_FILE):
                    os.remove(ACTIVE_FILE)
            except OSError:
                pass

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
