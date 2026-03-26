#!/usr/bin/env python3
"""PostToolUse hook: correct incomplete agent deliverables.

Strengthens the Correct verb. When an agent's output covers fewer tasks/items
than its prompt specified, emits correction instructions (not just a warning).

Complements plan-completeness-check.py (Verify verb) which checks F-numbers.
This hook checks task counts and enumerated item completion.
"""
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
MAX_AGE_SECONDS = 7200

# Patterns for extracting expected counts from prompts
TASK_COUNT_PATTERNS = [
    re.compile(r'(\d+)\s+tasks?\b', re.I),
    re.compile(r'tasks?\s+(\d+)\s+(?:through|to|-)\s+(\d+)', re.I),
    re.compile(r'Task\s+\d+\s+of\s+(\d+)', re.I),
]

# Pattern for numbered list items (1. xxx, 2. xxx)
NUMBERED_LIST = re.compile(r'^\s*(\d+)\.\s+\S', re.M)

# Completion claims in output
COMPLETION_CLAIMS = re.compile(
    r'(?:completed?|done|finished|implemented)\s+(?:all\s+)?(\d+)',
    re.I,
)

# Placeholder markers that indicate unfinished work
PLACEHOLDER_PATTERNS = [
    re.compile(r'\bTODO\b', re.I),
    re.compile(r'\bFIXME\b', re.I),
    re.compile(r'\bHACK\b', re.I),
    re.compile(r'\bplaceholder\b', re.I),
    re.compile(r'\bnot implemented\b', re.I),
    re.compile(r'\bstub\b', re.I),
    re.compile(r'//\s*\.\.\.', re.I),
    re.compile(r'pass\s+#\s', re.I),
]


def detect_placeholders(result: str) -> list[str]:
    """Return a list of placeholder marker strings found in agent output."""
    found = []
    for pattern in PLACEHOLDER_PATTERNS:
        match = pattern.search(result)
        if match:
            found.append(match.group(0))
    return found


def is_session_active() -> bool:
    """Check if session file exists and is less than 2 hours old."""
    try:
        data = json.loads(SESSION_FILE.read_text())
        ts = data.get("ts", 0)
        return (time.time() - ts) < MAX_AGE_SECONDS
    except (json.JSONDecodeError, KeyError, OSError):
        return False


def extract_expected_count(prompt: str) -> int | None:
    """Extract the expected number of tasks/items from the prompt."""
    for pattern in TASK_COUNT_PATTERNS:
        match = pattern.search(prompt)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                # "tasks 3 to 7" -> 5 tasks
                return int(groups[1]) - int(groups[0]) + 1
            return int(groups[0])

    # Fall back to counting numbered list items
    numbers = [int(m) for m in NUMBERED_LIST.findall(prompt)]
    if len(numbers) >= 3:
        return max(numbers)

    return None


def extract_completed_count(result: str) -> int | None:
    """Extract how many items the agent claims to have completed."""
    match = COMPLETION_CLAIMS.search(result)
    if match:
        return int(match.group(1))
    return None


def main():
    data = parse_event()
    if not data:
        return

    if get_tool_name(data) != "Agent":
        return

    if not is_session_active():
        return

    prompt = get_tool_input(data).get("prompt", "")
    result = get_tool_result(data)

    if not prompt or not result:
        return

    expected = extract_expected_count(prompt)

    if expected is not None and expected >= 2:
        completed = extract_completed_count(result)

        if completed is not None and completed < expected:
            advisory(
                f"CORRECTION: Agent completed {completed}/{expected} items. "
                f"Re-dispatch the Agent tool for the remaining {expected - completed} items. "
                f"Do NOT accept partial delivery. "
                f"Known rationalization: 'The pattern is established, remaining items follow the same approach' "
                f"— this is the #1 cause of incomplete deliverables. Every item must be explicitly completed."
            )

    # Placeholder detection — catch residual unfinished work
    placeholders = detect_placeholders(result)
    if placeholders:
        markers = ", ".join(placeholders[:5])
        advisory(
            f"CORRECTION: Agent output contains placeholder markers: {markers}. "
            f"These indicate unfinished work. Complete all TODO/FIXME/HACK items "
            f"before claiming completion. "
            f"Known rationalization: 'I'll clean these up in a follow-up' "
            f"— placeholders left in delivered code are never cleaned up."
        )


if __name__ == "__main__":
    main()
