#!/usr/bin/env python3
"""Claude Code PreToolUse hook: warn when orchestrator edits code files during Phase 5.

During the execution phase, code changes should be delegated to agents.
The orchestrator may edit docs/memory/.md files directly, but editing
source code files suggests the orchestrator is bypassing delegation.

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


def is_docs_or_md(file_path: str) -> bool:
    """Return True if the file is markdown or a file under top-level docs/memory dirs.

    Only exempts .md files unconditionally. For docs/ and memory/ directories,
    requires the segment to appear as a top-level directory (first real path
    component after any leading / or drive) to avoid false positives on paths
    like src/memory/cache.py or pkg/docs/parser.py.
    """
    p = Path(file_path)
    if p.suffix == ".md":
        return True
    # Only exempt if docs or memory is a top-level directory segment
    # (i.e., the path starts with docs/ or memory/ relative to the working dir)
    parts = p.parts
    # For absolute paths, check index 1 (after '/'); for relative, check index 0
    top_index = 1 if parts and parts[0] == "/" else 0
    if len(parts) > top_index and parts[top_index] in ("docs", "memory"):
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

    if is_docs_or_md(file_path):
        # Docs/memory/md files are fine for orchestrator to edit directly
        return

    # Code file during execution phase — warn
    print(json.dumps({
        "decision": "allow",
        "reason": (
            f"You are the orchestrator. During execution phase, you delegate code changes — you do not make them directly. "
            f"Use the Agent tool to dispatch this edit of {file_path}. "
            f"Known rationalization: 'It's a small change, faster to do it myself' — size does not exempt delegation rules."
        ),
    }))


if __name__ == "__main__":
    main()
