#!/usr/bin/env python3
"""UserPromptSubmit handler: surface pending CI-failure markers into this turn.

Invoked in-process by prompt-dispatcher.py (added to HOOK_PATHS). Reads any
failure markers written by ci-watcher.py under the primary failures dir AND the
system-temp fallback dir (ci-watcher.py durably writes to whichever it can), prints
them to stdout as a system note (which Claude Code injects as context for the
current turn), then DELETES each SURFACED marker (consume-once). A corrupt or
bad-schema marker becomes a NON-consuming warning (left in place for inspection),
isolated per-marker so one bad file never suppresses the good ones. Never blocks a
prompt; always exits 0.

This is the Correct-tier half of the post-push CI watcher: it closes the loop by
putting the delayed CI failure back in front of Claude without Claude having to
remember to look. See harness decision post-push-ci-watch-2026-07-09.

Escape hatch: CT_CI_WATCH_DISABLE=1 -> no-op.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
FAILURES_DIR = HOME / ".claude" / "ci-watch" / "failures"
FALLBACK_DIR = Path(tempfile.gettempdir()) / "ci-watch-failures"


def _format_marker(marker):
    """Render one marker as a concise human+agent-readable note, or None when the
    marker is not a dict / lacks the required repo+branch schema (caller warns)."""
    if not isinstance(marker, dict):
        return None
    repo = marker.get("repo")
    branch = marker.get("branch")
    if repo is None or branch is None:
        return None
    jobs = marker.get("failed_jobs") or []
    names = ", ".join(j if isinstance(j, str) else j.get("name", "?") for j in jobs) or "(run)"
    lines = [f"CI FAILED after a push you made: {repo} on {branch}",
             f"  Failed job(s): {names}"]
    if marker.get("run_url"):
        lines.append(f"  Run: {marker['run_url']}")
    lines.append("  This failed AFTER the fast checks were green. Investigate or escalate "
                 "-- do not ignore it (see feedback_no_merge_past_unrelated_ci_red).")
    return "\n".join(lines)


def main():
    if os.environ.get("CT_CI_WATCH_DISABLE") == "1":
        return
    try:
        sys.stdin.read()
    except OSError:
        pass
    markers = []
    for directory in (FAILURES_DIR, FALLBACK_DIR):
        try:
            if directory.is_dir():
                markers.extend(sorted(directory.glob("*.json")))
        except OSError:
            continue
    notes = []
    consumed = []
    for path in markers:
        try:
            marker = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            notes.append(f"[ci-watch] WARNING: unreadable marker {path.name} — left in place; "
                         f"inspect {path.parent}.")
            continue
        formatted = _format_marker(marker)
        if formatted is None:
            notes.append(f"[ci-watch] WARNING: malformed marker {path.name} (bad schema) — left "
                         f"in place; inspect {path.parent}.")
            continue
        notes.append(formatted)
        consumed.append(path)
    if notes:
        print(f"[post-push CI watcher] {len(notes)} CI note(s) since your last turn:")
        print("\n\n".join(notes))
    for path in consumed:                               # consume ONLY after output
        try:
            path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - context injection must never block a prompt
        pass
    sys.exit(0)
