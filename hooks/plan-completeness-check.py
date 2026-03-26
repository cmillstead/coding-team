#!/usr/bin/env python3
"""PostToolUse hook: warn when agent output covers fewer findings than input specified."""
import json
import re
import sys
import time
from pathlib import Path

SESSION_FILE = Path("/tmp/coding-team-session.json")
MAX_AGE_SECONDS = 7200  # 2 hours
FINDING_PATTERN = re.compile(r'F(\d+)')


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
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    if data.get("tool_name") != "Agent":
        return

    if not is_session_active():
        return

    prompt = data.get("tool_input", {}).get("prompt", "")
    input_findings = extract_finding_numbers(prompt)
    if not input_findings:
        return

    result = data.get("tool_result", "")
    if not result:
        return

    output_findings = extract_finding_numbers(result)
    found = input_findings & output_findings
    missing = sorted(input_findings - output_findings, key=lambda x: int(x))

    if len(found) < len(input_findings):
        missing_list = ", ".join(f"F{n}" for n in missing)
        print(json.dumps({
            "decision": "allow",
            "reason": (
                f"COMPLETENESS WARNING: Agent output covers {len(found)}/{len(input_findings)} "
                f"findings. Missing: {missing_list}. Re-check agent output before accepting."
            ),
        }))


if __name__ == "__main__":
    main()
