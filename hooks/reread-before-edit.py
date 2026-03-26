#!/usr/bin/env python3
"""Claude Code PreToolUse hook: warn if editing a file not recently Read.

Tracks Read calls in /tmp/claude-reread-tracker.json with a global counter.
When an Edit is attempted on a file not Read in the last 30 tool calls,
emits an advisory warning. Never blocks — decision is always "allow".
"""

import hashlib
import json
import os
import sys


def _get_state_file():
    session_id = os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "default"))
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return f'/tmp/claude-reread-tracker-{h}.json'


STATE_FILE = _get_state_file()
STALENESS_THRESHOLD = 30


def load_state() -> dict:
    """Load tracker state, returning fresh state on any error."""
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        # Validate structure
        if not isinstance(state, dict):
            return {'counter': 0, 'files': {}}
        if 'counter' not in state or 'files' not in state:
            return {'counter': 0, 'files': {}}
        return state
    except (OSError, json.JSONDecodeError, TypeError):
        return {'counter': 0, 'files': {}}


def save_state(state: dict) -> None:
    """Persist tracker state, ignoring write errors."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except OSError:
        pass


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        # Malformed input — allow silently
        print(json.dumps({"decision": "allow"}))
        return

    tool_name = event.get('tool_name', '')
    tool_input = event.get('tool_input', {})

    # Only care about Read and Edit
    if tool_name not in ('Read', 'Edit'):
        return

    state = load_state()
    state['counter'] = state.get('counter', 0) + 1
    counter = state['counter']

    file_path = tool_input.get('file_path', '')
    if not file_path:
        save_state(state)
        return

    # Normalize the path
    file_path = os.path.normpath(file_path)

    if tool_name == 'Read':
        # Track the Read
        state['files'][file_path] = counter
        save_state(state)
        # Silent allow — no output needed for Read
        return

    # tool_name == 'Edit'
    last_read = state.get('files', {}).get(file_path)
    save_state(state)

    if last_read is None:
        print(json.dumps({
            "decision": "allow",
            "reason": f"STALE CONTEXT: Editing {file_path} without a prior Read. "
                      f"Use the Read tool on {file_path} first to avoid overwriting external changes."
        }))
    elif (counter - last_read) > STALENESS_THRESHOLD:
        age = counter - last_read
        print(json.dumps({
            "decision": "allow",
            "reason": f"STALE CONTEXT: Last Read of {file_path} was {age} tool calls ago "
                      f"(threshold: {STALENESS_THRESHOLD}). Use the Read tool on {file_path} before "
                      f"this Edit to avoid overwriting external changes."
        }))
    else:
        # Recently read — allow silently
        print(json.dumps({"decision": "allow"}))


if __name__ == '__main__':
    main()
