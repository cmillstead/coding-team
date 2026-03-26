#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block orchestrator edits to non-allowlisted files during Phase 5.

During the execution phase, all file edits should be delegated to agents.
The orchestrator may only edit memory files (memory/), the Obsidian vault
(~/Documents/obsidian-vault/), and /tmp/ session files directly.
Everything else — including agents/, phases/, prompts/, skills/, hooks/,
docs/plans/, and source code — must go through the Agent tool.

State file: /tmp/coding-team-session.json
Format: {"phase": "execution", "ts": 1234567890}

Degrades gracefully when the session file is absent or malformed.
"""

import json
import sys
import time
from pathlib import Path

SESSION_FILE = Path("/tmp/coding-team-session.json")
MAX_AGE_SECONDS = 2 * 60 * 60  # 2 hours


def is_orchestrator_file(file_path: str) -> bool:
    """Return True only for files the orchestrator may edit during Phase 5.

    Allowlist: memory/, ~/Documents/obsidian-vault/, /tmp/ session files.
    Everything else (agents/, phases/, prompts/, skills/, hooks/, docs/plans/,
    source code) must be dispatched to agents via the Agent tool.
    """
    path_str = str(file_path)

    # /tmp/ session files are always allowed
    if path_str.startswith("/tmp"):
        return True

    # Obsidian vault is allowed
    if "/Documents/obsidian-vault/" in path_str:
        return True

    # memory/ directory is allowed — check for /memory/ anywhere in path
    # because project memory paths are absolute: ~/.claude/projects/.../memory/
    if "/memory/" in path_str or path_str.endswith("/memory"):
        return True

    return False


def read_session() -> tuple[dict | None, bool]:
    """Read and validate the session file.

    Returns (session_dict, had_error).
    - (dict, False) on success
    - (None, False) when file absent or session expired
    - (None, True) when file exists but is corrupt or missing keys
    """
    if not SESSION_FILE.exists():
        return None, False

    try:
        data = json.loads(SESSION_FILE.read_text())
    except json.JSONDecodeError:
        return None, True
    except OSError:
        return None, False

    try:
        phase = data["phase"]
        ts = data["ts"]
    except KeyError:
        return None, True

    # Check staleness
    if time.time() - ts > MAX_AGE_SECONDS:
        return None, False

    return {"phase": phase, "ts": ts}, False


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print(json.dumps({"decision": "allow"}))
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    # Only trigger on Edit and Write
    if tool_name not in ("Edit", "Write"):
        return

    session, had_error = read_session()
    if had_error:
        # Corrupt session file — explicit graceful degradation
        print(json.dumps({"decision": "allow"}))
        return
    if session is None:
        # No session file or expired — silent allow
        return

    if session["phase"] != "execution":
        # Not in execution phase — silent allow
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    if is_orchestrator_file(file_path):
        # Memory/vault/tmp files are fine for orchestrator to edit directly
        return

    # Code file during execution phase — BLOCK (not warn)
    # Warnings are routinely ignored under context pressure (feedback-warnings-escape-hatch.md).
    # Constrain > Inform: make it impossible, don't ask nicely.
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"BLOCKED: During execution phase, the orchestrator delegates all file edits — never makes them directly. "
            f"Use the Agent tool to dispatch this edit of {file_path}. "
            f"For agent/phase/prompt/skill files, include PROMPT_CRAFT_ADVISORY in the agent prompt. "
            f"Only memory/, ~/Documents/obsidian-vault/, and /tmp/ are orchestrator-editable during Phase 5."
        ),
    }))


if __name__ == "__main__":
    main()
