#!/usr/bin/env python3
"""PreToolUse hook: injects codesight-mcp search instructions into Agent prompts."""

import json
import sys

CODESIGHT_INSTRUCTION = (
    "\n\nMANDATORY SEARCH RULES: This repo is indexed in codesight-mcp. "
    "DO NOT use Grep, Bash grep, rg, or find to search code. "
    "Use mcp__codesight-mcp__search_text for text search and "
    "mcp__codesight-mcp__search_symbols for symbol search. "
    "Fetch these tools via ToolSearch first."
)


def main():
    hook_input = json.load(sys.stdin)
    tool_input = hook_input.get("tool_input", {})
    prompt = tool_input.get("prompt", "")

    if not prompt:
        return

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": {"prompt": prompt + CODESIGHT_INSTRUCTION},
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
