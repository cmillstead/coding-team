#!/usr/bin/env python3
"""SessionStart hook: audit settings.json deny-list completeness.

Checks that the deny list in ~/.claude/settings.json covers all known
sensitive paths. Reports gaps — missing paths mean sensitive areas
could be accidentally modified.

Advisory only — does not block the session.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.output import advisory
from _lib.suppression import is_recently_clean, mark_clean

SUPPRESSION_KEY = "deny_list_last_clean"

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# Required deny patterns — these sensitive paths must be protected
REQUIRED_DENY_PATTERNS = [
    "~/.ssh",
    "~/.aws",
    "~/.config/gcloud",
    "~/.kube",
    "~/.azure",
    "~/Library/Keychains",
    "~/.password-store",
    "~/.gnupg",
]


def load_deny_list() -> list[str]:
    """Load the deny list from settings.json."""
    try:
        with open(SETTINGS_PATH) as f:
            settings = json.load(f)
        return settings.get("permissions", {}).get("deny", [])
    except (json.JSONDecodeError, OSError, KeyError):
        return []


def check_deny_coverage(deny_list: list[str]) -> list[str]:
    """Check which required patterns are missing from the deny list.

    Returns list of missing pattern descriptions.
    """
    # Normalize deny list entries for matching
    deny_text = " ".join(deny_list).lower()

    missing = []
    for pattern in REQUIRED_DENY_PATTERNS:
        # Check if the pattern appears in any deny entry
        # Normalize: ~/.ssh -> .ssh, ~/Library -> Library
        key = pattern.lstrip("~/").lower()
        if key not in deny_text:
            missing.append(pattern)

    return missing


def main():
    if is_recently_clean(SUPPRESSION_KEY):
        return  # Clean within 24h — suppress advisory

    deny_list = load_deny_list()

    if not deny_list:
        advisory(
            "Settings deny-list is EMPTY. No sensitive paths are protected. "
            "Add deny rules for: " + ", ".join(REQUIRED_DENY_PATTERNS)
        )
        return

    missing = check_deny_coverage(deny_list)
    if not missing:
        mark_clean(SUPPRESSION_KEY)
        return  # All required patterns covered — silent success

    advisory(
        f"Settings deny-list gaps: {len(missing)} sensitive path(s) not covered.\n"
        + "\n".join(f"  - {p}" for p in missing)
        + "\n\nAdd Edit() and Read() deny rules for these paths in ~/.claude/settings.json"
    )


if __name__ == "__main__":
    main()
