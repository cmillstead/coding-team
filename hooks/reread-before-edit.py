#!/usr/bin/env python3
"""Claude Code PreToolUse hook: warn if editing a file not recently Read.

Tracks Read calls in /tmp/claude-reread-tracker.json with a global counter.
When an Edit is attempted on a file not Read in the last 30 tool calls,
emits an advisory warning. Never blocks — decision is always "allow".
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _lib.event import parse_event, get_tool_name, get_tool_input, get_file_path
from _lib.output import allow, advisory
from _lib.state import get_state_file, load_state, save_state


STATE_FILE = get_state_file("claude-reread-tracker")
STALENESS_THRESHOLD = 30


def _load_tracker_state() -> dict:
    """Load tracker state, returning fresh state on any error."""
    state = load_state(STATE_FILE, default={'counter': 0, 'files': {}})
    # Validate structure
    if 'counter' not in state or 'files' not in state:
        return {'counter': 0, 'files': {}}
    return state


def _save_tracker_state(state: dict) -> None:
    """Persist tracker state."""
    save_state(STATE_FILE, state)


def main():
    event = parse_event()
    if not event:
        # Malformed input — allow silently
        allow()
        return

    tool_name = get_tool_name(event)

    # Only care about Read and Edit
    if tool_name not in ('Read', 'Edit'):
        return

    state = _load_tracker_state()
    state['counter'] = state.get('counter', 0) + 1
    counter = state['counter']

    file_path = get_file_path(event)
    if not file_path:
        _save_tracker_state(state)
        return

    # Normalize the path
    file_path = os.path.normpath(file_path)

    if tool_name == 'Read':
        # Track the Read
        state['files'][file_path] = counter
        _save_tracker_state(state)
        # Silent allow — no output needed for Read
        return

    # tool_name == 'Edit'
    last_read = state.get('files', {}).get(file_path)
    _save_tracker_state(state)

    if last_read is None:
        advisory(
            f"STALE CONTEXT: Editing {file_path} without a prior Read. "
            f"Use the Read tool on {file_path} first to avoid overwriting external changes."
        )
    elif (counter - last_read) > STALENESS_THRESHOLD:
        age = counter - last_read
        advisory(
            f"STALE CONTEXT: Last Read of {file_path} was {age} tool calls ago "
            f"(threshold: {STALENESS_THRESHOLD}). Use the Read tool on {file_path} before "
            f"this Edit to avoid overwriting external changes."
        )
    else:
        # Recently read — allow silently
        allow()


if __name__ == '__main__':
    main()
