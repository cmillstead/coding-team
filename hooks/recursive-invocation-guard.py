#!/usr/bin/env python3
"""PreToolUse hook: block recursive /coding-team invocation."""
import json
import os
import sys


ACTIVE_FILE = "/tmp/coding-team-active"


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"decision": "allow"}))
        return

    tool_name = data.get("tool_name", "")
    if tool_name != "Skill":
        print(json.dumps({"decision": "allow"}))
        return

    skill_name = data.get("tool_input", {}).get("skill", "")
    if skill_name != "coding-team":
        print(json.dumps({"decision": "allow"}))
        return

    if os.path.exists(ACTIVE_FILE):
        print(json.dumps({
            "decision": "block",
            "reason": "You are already inside the coding-team pipeline. Do not invoke /coding-team recursively. Complete the current task within the existing pipeline."
        }))
        return

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
