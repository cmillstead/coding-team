#!/usr/bin/env python3
"""UserPromptSubmit hook: suggest /coding-team for code tasks.

Lightweight session-start router. Fires on first user message only
(tracked via session state file). Reminds Claude that coding-team
is the primary skill for code work without being aggressive.
"""

import hashlib
import json
import os
import sys
import time

STATE_DIR = "/tmp"


def get_state_file() -> str:
    session_id = os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "default"))
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return os.path.join(STATE_DIR, f"coding-team-router-{h}.json")


def main():
    state_file = get_state_file()

    # Only fire once per session
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
            if time.time() - state.get("ts", 0) < 7200:  # 2hr session window
                return
        except (json.JSONDecodeError, OSError):
            pass

    # Mark as fired
    with open(state_file, "w") as f:
        json.dump({"ts": time.time()}, f)

    # Read the user's prompt
    event = json.load(sys.stdin)
    prompt = event.get("user_prompt", event.get("prompt", "")).lower()

    # Skip for non-code tasks, greetings, and meta questions
    skip_patterns = [
        "help", "hello", "hi ", "hey", "what can you",
        "how do i", "/", "remember", "forget", "save",
        "mcp", "status", "config", "setting",
    ]
    if any(prompt.startswith(p) or p in prompt[:30] for p in skip_patterns):
        return

    # Suggest coding-team
    print(json.dumps({
        "additionalContext": (
            "<user-prompt-submit-hook>\n"
            "SKILL ROUTER: For non-trivial code tasks (features, refactors, bug fixes), "
            "use the coding-team skill (`/coding-team`). It handles design, planning, "
            "execution, and shipping end-to-end. For simple mechanical tasks, just do them directly. "
            "Match process weight to task weight.\n"
            "</user-prompt-submit-hook>"
        )
    }))


if __name__ == "__main__":
    main()
