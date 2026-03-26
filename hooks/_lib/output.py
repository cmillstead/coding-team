"""Output formatting utilities for Claude Code hooks."""

import json


def block(reason: str) -> None:
    """Print a block decision."""
    print(json.dumps({"decision": "block", "reason": reason}))


def allow() -> None:
    """Print an allow decision."""
    print(json.dumps({"decision": "allow"}))


def allow_with_reason(reason: str) -> None:
    """Print an allow decision with advisory reason."""
    print(json.dumps({"decision": "allow", "reason": reason}))


def advisory(reason: str) -> None:
    """Print an advisory (allow with reason). Semantic alias for allow_with_reason."""
    allow_with_reason(reason)


def update_input(tool_input: dict) -> None:
    """Print an allow decision with updated tool input."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": tool_input,
        }
    }))
