#!/usr/bin/env python3
"""Claude Code PostToolUse hook: track agent/skill quality signals.

Fires after Skill tool completes. Logs outcome signals to
~/.claude/metrics/agent-quality-{date}.jsonl for trend analysis.

Signals captured:
- Skill name and duration (if available)
- Whether the skill produced output or errored
- Session context (session ID, timestamp)
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    if tool_name != "Skill":
        return

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})

    skill_name = tool_input.get("skill_name", tool_input.get("skill", "unknown"))

    result_str = ""
    if isinstance(tool_result, dict):
        result_str = tool_result.get("stdout", "") + tool_result.get("stderr", "")
    elif isinstance(tool_result, str):
        result_str = tool_result

    has_output = len(result_str.strip()) > 0
    has_error = False
    if isinstance(tool_result, dict):
        exit_code = tool_result.get("exit_code")
        if exit_code is not None and exit_code != 0:
            has_error = True
    if any(marker in result_str.lower() for marker in ["error", "traceback", "exception"]):
        has_error = True

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = METRICS_DIR / f"agent-quality-{today}.jsonl"

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill": skill_name,
        "has_output": has_output,
        "has_error": has_error,
        "output_length": len(result_str),
        "session": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    main()
