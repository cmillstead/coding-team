#!/usr/bin/env python3
"""UserPromptSubmit hook: suggest /coding-team for code tasks.

Lightweight session-start router. Fires on first user message only
(tracked via session state file). Reminds Claude that coding-team
is the primary skill for code work without being aggressive.

Also detects in-progress coding-team work (plan files, state files,
feature branches) and suggests `/coding-team continue` to resume.
"""

import glob
import hashlib
import json
import os
import subprocess
import sys
import time

STATE_DIR = "/tmp"


def get_state_file() -> str:
    session_id = os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "default"))
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return os.path.join(STATE_DIR, f"coding-team-router-{h}.json")


def get_main_repo_root() -> str | None:
    """Find the main repo root (not a worktree)."""
    try:
        git_common = subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if git_common.endswith("/.git"):
            return git_common[:-5]
        return git_common
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def check_progress() -> str | None:
    """Check for in-progress coding-team work.

    Returns:
        "in-progress" if a state file exists (approach approved, pre-spec)
        "on-feature-branch" if on a feat/ or feature/ branch
        "has-plans" if plan files exist in docs/plans/
        None if no in-progress work detected
    """
    main_root = get_main_repo_root()
    if not main_root:
        return None

    # Check for lightweight state file (Phase 1 approach approved)
    state_file = os.path.join(main_root, "docs", "plans", ".coding-team-state")
    if os.path.exists(state_file):
        return "in-progress"

    # Check for plan files
    plans = glob.glob(os.path.join(main_root, "docs", "plans", "*.md"))
    if not plans:
        return None

    # Check if on a feature branch (strongest signal of active work)
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            text=True, stderr=subprocess.DEVNULL
        ).strip()
        if branch.startswith("feat/") or branch.startswith("feature/"):
            return "on-feature-branch"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return "has-plans"


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

    # Check for in-progress coding-team work
    progress = check_progress()

    if progress in ("in-progress", "on-feature-branch"):
        print(json.dumps({
            "additionalContext": (
                "<user-prompt-submit-hook>\n"
                "SKILL ROUTER: Detected in-progress coding-team work. "
                "Suggest the user run `/coding-team continue` to resume where they left off. "
                "The router will find the plan, detect progress from git commits, and print a recovery block.\n"
                "</user-prompt-submit-hook>"
            )
        }))
    elif progress == "has-plans":
        print(json.dumps({
            "additionalContext": (
                "<user-prompt-submit-hook>\n"
                "SKILL ROUTER: Found existing plan files in docs/plans/. "
                "If the user is continuing prior work, suggest `/coding-team continue`. "
                "For new non-trivial code tasks, use `/coding-team`. "
                "For simple mechanical tasks, just do them directly.\n"
                "</user-prompt-submit-hook>"
            )
        }))
    else:
        # Default: suggest coding-team for code tasks
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
