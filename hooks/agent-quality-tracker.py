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

sys.path.insert(0, os.path.dirname(__file__))
from _lib.event import parse_event, get_tool_name, get_tool_result
from _lib.output import allow_with_reason

METRICS_DIR = Path.home() / ".claude" / "metrics"


def main():
    event = parse_event()
    if not event:
        return

    if get_tool_name(event) != "Skill":
        return

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})

    skill_name = tool_input.get("skill_name", tool_input.get("skill", "unknown"))

    result_str = get_tool_result(event)

    has_output = len(result_str.strip()) > 0
    has_error = False
    if isinstance(tool_result, dict):
        exit_code = tool_result.get("exit_code")
        if exit_code is not None and exit_code != 0:
            has_error = True
        elif exit_code is None:
            # No exit code available — fall back to keyword detection
            if any(marker in result_str.lower() for marker in ["error", "traceback", "exception"]):
                has_error = True
        # If exit_code == 0, trust the exit code over keywords
    elif any(marker in result_str.lower() for marker in ["error", "traceback", "exception"]):
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

    if has_error:
        allow_with_reason(
            f"QUALITY GATE: Skill '{skill_name}' errored. Do NOT accept output without verifying every deliverable. "
            f"Known rationalization: 'The error is non-fatal, output is mostly correct' — partial output from errored skills contains silent omissions. "
            f"Re-dispatch using the Skill tool with a narrower prompt or escalated model tier."
        )
        return

    if not has_output:
        allow_with_reason(
            f"QUALITY GATE: Skill '{skill_name}' produced no output — likely silent failure. "
            f"Re-dispatch using the Skill tool. Do not assume the task completed."
        )
        return


if __name__ == "__main__":
    main()
