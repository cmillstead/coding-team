#!/usr/bin/env python3
"""PreToolUse hook: block git commit/push/merge on main/master."""
import json
import re
import subprocess
import sys


PROTECTED_BRANCHES = {"main", "master"}
GIT_PATTERN = re.compile(r'\bgit\s+(commit|push|merge)\b')


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps({"decision": "allow"}))
        return

    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        print(json.dumps({"decision": "allow"}))
        return

    command = data.get("tool_input", {}).get("command", "")
    if not GIT_PATTERN.search(command):
        print(json.dumps({"decision": "allow"}))
        return

    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            # Not in a git repo — allow through
            print(json.dumps({"decision": "allow"}))
            return

        branch = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Can't determine branch — allow through
        print(json.dumps({"decision": "allow"}))
        return

    if branch in PROTECTED_BRANCHES:
        print(json.dumps({
            "decision": "block",
            "reason": f"Create a feature branch first. Direct commits to {branch} are not allowed. Run: git checkout -b <feature-name>"
        }))
        return

    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
