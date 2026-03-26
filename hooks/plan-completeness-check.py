#!/usr/bin/env python3
"""PostToolUse hook: warn when agent output covers fewer findings than input specified."""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.event import parse_event, get_tool_name, get_tool_input, get_tool_result
from _lib.output import advisory

SESSION_FILE = Path("/tmp/coding-team-session.json")
MAX_AGE_SECONDS = 7200  # 2 hours
FINDING_PATTERN = re.compile(r'\bF(\d{1,3})\b')


def is_session_active() -> bool:
    """Check if session file exists and is less than 2 hours old."""
    try:
        data = json.loads(SESSION_FILE.read_text())
        ts = data.get("ts", 0)
        return (time.time() - ts) < MAX_AGE_SECONDS
    except (json.JSONDecodeError, KeyError, OSError):
        return False


def extract_finding_numbers(text: str) -> set[str]:
    """Extract all F-numbers (e.g. F1, F12) from text."""
    return set(FINDING_PATTERN.findall(text))


def main():
    data = parse_event()
    if not data:
        return

    if get_tool_name(data) != "Agent":
        return

    if not is_session_active():
        return

    prompt = get_tool_input(data).get("prompt", "")
    input_findings = extract_finding_numbers(prompt)
    if not input_findings:
        return

    result = get_tool_result(data)
    if not result:
        return

    output_findings = extract_finding_numbers(result)
    found = input_findings & output_findings
    missing = sorted(input_findings - output_findings, key=lambda x: int(x))

    if len(found) < len(input_findings):
        missing_list = ", ".join(f"F{n}" for n in missing)
        advisory(
            f"COMPLETENESS GATE: Agent covered {len(found)}/{len(input_findings)} findings. "
            f"Missing: {missing_list}. Re-dispatch the Agent tool for missing findings specifically — "
            f"do not accept partial coverage. "
            f"Known rationalization: 'The missing ones are minor' — all assigned findings must be addressed."
        )


if __name__ == "__main__":
    main()
