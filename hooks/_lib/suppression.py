"""Cross-session advisory suppression for SessionStart hooks.

Tracks when advisory checks last returned clean. If a check was clean
within 24 hours, the hook can skip output to reduce advisory fatigue.
Uses a fixed path (not session-scoped) since suppression spans sessions.
"""

import json
import time
from pathlib import Path

SUPPRESSION_FILE = Path("/tmp/ct-advisory-suppression.json")


def is_recently_clean(key: str, max_age: int = 86400) -> bool:
    """Check if this advisory was clean within max_age seconds (default 24h)."""
    try:
        data = json.loads(SUPPRESSION_FILE.read_text())
        ts = data.get(key)
        if ts and (time.time() - ts) < max_age:
            return True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return False


def mark_clean(key: str) -> None:
    """Record that this advisory check was clean just now."""
    try:
        data = json.loads(SUPPRESSION_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data[key] = time.time()
    try:
        SUPPRESSION_FILE.write_text(json.dumps(data))
    except OSError:
        pass
