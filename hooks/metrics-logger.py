#!/usr/bin/env python3
"""Claude Code PostToolUse hook: logs tool usage metrics to daily JSONL files."""
import json
import os
import sys
from datetime import datetime, timezone


def extract_file(tool_input):
    """Extract file path from tool_input if available."""
    if not tool_input or not isinstance(tool_input, dict):
        return None
    # Direct file_path field (Read, Edit, Write)
    if "file_path" in tool_input:
        return tool_input["file_path"]
    # Command field — extract first path-like argument
    if "command" in tool_input:
        parts = tool_input["command"].split()
        for part in parts:
            if part.startswith("/"):
                return part
    # Pattern field (Glob)
    if "pattern" in tool_input and "path" in tool_input:
        return tool_input["path"]
    return None


def main():
    try:
        event = json.load(sys.stdin)
        tool_name = event.get("tool_name", "unknown")
        tool_input = event.get("tool_input", {})

        metrics_dir = os.path.expanduser("~/.claude/metrics")
        os.makedirs(metrics_dir, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = os.path.join(metrics_dir, f"tool-usage-{today}.jsonl")

        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": tool_name,
            "file": extract_file(tool_input),
            "session": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        }

        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


if __name__ == "__main__":
    main()
