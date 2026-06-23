"""Event parsing utilities for Claude Code hooks."""

import json
import sys


def parse_event() -> dict:
    """Read and parse JSON event from stdin."""
    try:
        return json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def get_tool_name(event: dict) -> str:
    """Extract tool name from event."""
    return event.get("tool_name", "")


def get_tool_input(event: dict) -> dict:
    """Extract tool input from event with type guard."""
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return {}
    return tool_input


def get_tool_result(event: dict) -> str:
    """Normalize tool result to string.

    Reads the real PostToolUse key `tool_response` first (as captured by the
    live probe — see 01-02-PROBE-FINDING.md), then falls back to `tool_result`
    and `tool_output` for cross-version robustness.
    """
    result = event.get("tool_response", event.get("tool_result", event.get("tool_output", "")))
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        parts = []
        if "stdout" in result:
            parts.append(str(result["stdout"]))
        if "stderr" in result:
            parts.append(str(result["stderr"]))
        return "\n".join(parts) if parts else json.dumps(result)
    return str(result)


def get_command(event: dict) -> str:
    """Shortcut to get command from tool input."""
    return get_tool_input(event).get("command", "")


def get_file_path(event: dict) -> str:
    """Shortcut to get file_path from tool input."""
    return get_tool_input(event).get("file_path", "")
