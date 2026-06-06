"""Output formatting utilities for Claude Code hooks."""

import json

from .event import get_tool_input


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


def update_input(event: dict, partial: dict) -> None:
    """Print an allow decision with merged tool input.

    Merges `partial` over the event's original tool input.  CC's
    ``updatedInput`` fully replaces the tool input at the CC layer (it does
    not merge), so this helper performs the merge here: fields in `partial`
    win on key collision; all other original fields are preserved.

    Precondition: pass the same `event` whose `tool_input` the caller read.
    If `event` has no dict `tool_input`, there is nothing to merge over and
    the output contains only `partial` — the caller is responsible for
    validating the event before calling (the sole caller guards via an
    early return on empty prompt).
    """
    merged = {**get_tool_input(event), **partial}
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": merged,
        }
    }))
