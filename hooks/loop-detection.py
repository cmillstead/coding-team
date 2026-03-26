#!/usr/bin/env python3
"""Claude Code PostToolUse hook: detect doom loops.

Tracks recent Bash tool failures. If the same command pattern fails 3+
times in a session, injects a warning telling the agent to stop and
escalate instead of retrying blindly.

State is stored in /tmp/claude-loop-detection-{session_hash}.json
"""

import hashlib
import json
import os
import sys
import time

MAX_RETRIES = 3
STATE_DIR = "/tmp"
STALE_SECONDS = 3600  # clear state after 1 hour of inactivity


def get_state_file() -> str:
    session_id = os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "default"))
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return os.path.join(STATE_DIR, f"claude-loop-detection-{h}.json")


def load_state(path: str) -> dict:
    try:
        with open(path) as f:
            state = json.load(f)
        # Clear stale state
        if time.time() - state.get("last_updated", 0) > STALE_SECONDS:
            return {"failures": [], "last_updated": time.time()}
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return {"failures": [], "last_updated": time.time()}


def save_state(path: str, state: dict):
    state["last_updated"] = time.time()
    with open(path, "w") as f:
        json.dump(state, f)


def normalize_command(cmd: str) -> str:
    """Reduce command to a pattern for comparison."""
    # Strip whitespace, collapse paths to basenames
    parts = cmd.strip().split()
    if not parts:
        return cmd
    # Keep the command structure but normalize file paths
    normalized = []
    for part in parts[:5]:  # first 5 tokens are enough to identify the pattern
        if "/" in part and not part.startswith("-"):
            normalized.append(os.path.basename(part))
        else:
            normalized.append(part)
    return " ".join(normalized)


def main():
    event = json.load(sys.stdin)
    tool_name = event.get("tool_name", "")

    # Only track Bash tool results
    if tool_name != "Bash":
        return

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})
    command = tool_input.get("command", "")

    if not command:
        return

    # Check if the command failed (non-zero exit or error in output)
    stdout = tool_result.get("stdout", "") if isinstance(tool_result, dict) else str(tool_result)
    stderr = tool_result.get("stderr", "") if isinstance(tool_result, dict) else ""
    exit_code = tool_result.get("exit_code", 0) if isinstance(tool_result, dict) else None

    # Heuristic: detect failure from exit code or error patterns
    is_failure = False
    if exit_code is not None and exit_code != 0:
        is_failure = True
    elif any(marker in stdout.lower() for marker in ["error", "failed", "failure", "exception", "traceback"]):
        is_failure = True
    elif any(marker in stderr.lower() for marker in ["error", "failed", "failure"]):
        is_failure = True

    state_file = get_state_file()
    state = load_state(state_file)

    if is_failure:
        pattern = normalize_command(command)
        state["failures"].append({
            "pattern": pattern,
            "command": command[:200],
            "time": time.time(),
        })
        # Keep only last 20 failures
        state["failures"] = state["failures"][-20:]
        save_state(state_file, state)

        # Count recent failures with similar pattern
        recent = [f for f in state["failures"]
                  if f["pattern"] == pattern
                  and time.time() - f["time"] < 300]  # within 5 minutes

        if len(recent) >= MAX_RETRIES:
            msg = f"""DOOM LOOP DETECTED: The same command pattern has failed {len(recent)} times in the last 5 minutes.

Pattern: {pattern}

Recent failures:
"""
            for f in recent[-3:]:
                msg += f"  - {f['command'][:100]}\n"

            msg += """
STOP RETRYING. You are in a doom loop. Instead:
1. Describe what you were trying to accomplish
2. List the approaches you've tried and why they failed
3. Identify what you think the root cause is
4. Ask the user for guidance

Do NOT attempt the same fix again without explicit user direction."""

            # Don't block — just inject a strong warning
            print(json.dumps({
                "decision": "allow",
                "reason": msg,
            }))
            return
    else:
        # Success — clear failures for this pattern
        pattern = normalize_command(command)
        state["failures"] = [f for f in state["failures"] if f["pattern"] != pattern]
        save_state(state_file, state)


if __name__ == "__main__":
    main()
