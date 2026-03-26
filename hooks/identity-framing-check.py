#!/usr/bin/env python3
"""Claude Code PreToolUse hook: validate identity framing in agent/skill files.

Fires on Write. If the target file is an agent definition (.md in agents/)
or skill instruction (SKILL.md), checks that the content begins with
identity framing ("You are...").

Advisory only — allows the write but surfaces a warning if missing.
"""
import json
import re
import sys

IDENTITY_FILE_PATTERNS = [
    r"\.claude/agents/.*\.md$",
    r"\.claude/skills/.*/SKILL\.md$",
    r"agents/.*\.md$",
    r"skills/.*/SKILL\.md$",
]

IDENTITY_MARKERS = [
    r"^you are ",
    r"^your role",
    r"^as the ",
    r"^you serve as",
]


def is_instruction_file(file_path):
    """Check if the file path matches known instruction file patterns."""
    for pattern in IDENTITY_FILE_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def has_identity_framing(content):
    """Check if content starts with identity framing (after frontmatter/headers)."""
    if not content:
        return False

    lines = content.split("\n")
    in_frontmatter = False
    content_started = False

    for line in lines:
        stripped = line.strip()

        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue

        if not stripped:
            continue
        if stripped.startswith("#"):
            content_started = True
            continue

        if content_started or not stripped.startswith("#"):
            for marker in IDENTITY_MARKERS:
                if re.match(marker, stripped, re.IGNORECASE):
                    return True
            return False

    return False


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    if tool_name != "Write":
        return

    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    content = tool_input.get("content", "")

    if not file_path or not is_instruction_file(file_path):
        return

    if not has_identity_framing(content):
        msg = (
            f"Identity framing missing in {file_path}.\n"
            f"Agent/skill instruction files should start with identity framing: "
            f"'You are the [role]' — this sets behavioral defaults stronger than prohibitions.\n"
            f"See skill-files.md rule for guidance."
        )
        print(json.dumps({"decision": "allow", "reason": msg}))


if __name__ == "__main__":
    main()
