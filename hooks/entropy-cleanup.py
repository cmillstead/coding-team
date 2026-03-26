#!/usr/bin/env python3
"""SessionStart hook: detect entropy signals (stale files, large logs, orphans).

Reports entropy signals at session start. Does NOT auto-delete — surfaces
information for the user to act on. Supports Level 3→4 maturity bridge
by making entropy visible.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.output import advisory
from _lib.suppression import is_recently_clean, mark_clean

SUPPRESSION_KEY = "entropy_cleanup_last_clean"

METRICS_DIR = Path.home() / ".claude" / "metrics"
TMP_DIR = Path("/tmp")
STALE_THRESHOLD = 86400  # 24 hours
SESSION_STALE_THRESHOLD = 14400  # 4 hours
LARGE_FILE_THRESHOLD = 1_048_576  # 1 MB


def find_stale_state_files() -> list[str]:
    """Find claude-* and coding-team-* state files in /tmp older than 24h."""
    stale = []
    now = time.time()
    patterns = ["claude-*.json", "coding-team-*.json"]
    for pattern in patterns:
        for f in TMP_DIR.glob(pattern):
            try:
                if now - f.stat().st_mtime > STALE_THRESHOLD:
                    stale.append(f.name)
            except OSError:
                continue
    return stale[:10]  # Cap report at 10


def find_large_metrics_files() -> list[str]:
    """Find metrics log files larger than 1MB."""
    large = []
    if not METRICS_DIR.exists():
        return large
    for f in METRICS_DIR.glob("*.jsonl"):
        try:
            size = f.stat().st_size
            if size > LARGE_FILE_THRESHOLD:
                large.append(f"{f.name} ({size / 1_048_576:.1f}MB)")
        except OSError:
            continue
    return large


def find_orphan_sessions() -> list[str]:
    """Find coding-team-session.json files older than 4 hours."""
    orphans = []
    now = time.time()
    session_file = TMP_DIR / "coding-team-session.json"
    try:
        if session_file.exists():
            age = now - session_file.stat().st_mtime
            if age > SESSION_STALE_THRESHOLD:
                hours = age / 3600
                orphans.append(f"coding-team-session.json ({hours:.1f}h old)")
    except OSError:
        pass
    return orphans


def main():
    if is_recently_clean(SUPPRESSION_KEY):
        return  # Clean within 24h — suppress advisory

    signals = []

    stale = find_stale_state_files()
    if stale:
        signals.append(f"Stale state files in /tmp ({len(stale)}): {', '.join(stale[:5])}")

    large = find_large_metrics_files()
    if large:
        signals.append(f"Large metrics logs: {', '.join(large)}")

    orphans = find_orphan_sessions()
    if orphans:
        signals.append(f"Orphan session files: {', '.join(orphans)}")

    if not signals:
        mark_clean(SUPPRESSION_KEY)
        return  # Clean — silent success

    msg = "Entropy signals detected:\n" + "\n".join(f"- {s}" for s in signals)
    msg += "\n\nConsider cleaning up stale files: rm /tmp/claude-*.json /tmp/coding-team-*.json"
    advisory(msg)


if __name__ == "__main__":
    main()
