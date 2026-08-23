#!/usr/bin/env python3
"""UserPromptSubmit handler: surface pending CI-failure markers into this turn.

Invoked in-process by prompt-dispatcher.py (added to HOOK_PATHS). Reads any
failure markers written by ci-watcher.py under ~/.claude/ci-watch/failures/,
prints them to stdout as a system note (which Claude Code injects as context for
the current turn), then DELETES each marker (consume-once, so it surfaces exactly
one time). Never blocks a prompt; always exits 0.

This is the Correct-tier half of the post-push CI watcher: it closes the loop by
putting the delayed CI failure back in front of Claude without Claude having to
remember to look. See harness decision post-push-ci-watch-2026-07-09.

Escape hatch: CT_CI_WATCH_DISABLE=1 -> no-op.
"""

import json
import os
import sys
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
FAILURES_DIR = HOME / ".claude" / "ci-watch" / "failures"


def _format_marker(marker):
    """Render one marker as a concise human+agent-readable note."""
    repo = marker.get("repo", "?")
    branch = marker.get("branch", "?")
    run_url = marker.get("run_url", "")
    jobs = marker.get("failed_jobs", [])
    job_names = ", ".join(j.get("name", "?") for j in jobs) or "(unknown job)"
    lines = [
        f"CI FAILED after a push you made: {repo} @ {branch}",
        f"  Failed job(s): {job_names}",
    ]
    if run_url:
        lines.append(f"  Run: {run_url}")
    lines.append(
        "  This failed AFTER the fast checks were green. Investigate and fix or "
        "escalate to the user -- do not ignore it (see feedback_no_merge_past_"
        "unrelated_ci_red)."
    )
    return "\n".join(lines)


def main():
    if os.environ.get("CT_CI_WATCH_DISABLE") == "1":
        return
    try:
        # Drain stdin so the dispatcher hands us a clean pipe (we do not use it).
        sys.stdin.read()
    except OSError:
        pass
    try:
        if not FAILURES_DIR.is_dir():
            return
        markers = sorted(FAILURES_DIR.glob("*.json"))
    except OSError:
        return
    if not markers:
        return
    notes = []
    for path in markers:
        try:
            marker = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            try:
                path.unlink()
            except OSError:
                pass
            continue
        notes.append(_format_marker(marker))
        try:
            path.unlink()  # consume-once
        except OSError:
            pass
    if notes:
        banner = "[post-push CI watcher] " + str(len(notes)) + " CI failure(s) detected since your last turn:"
        print(banner)
        print("\n\n".join(notes))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - context injection must never block a prompt
        pass
    sys.exit(0)
