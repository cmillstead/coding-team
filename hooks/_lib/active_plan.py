"""Shared active-plan detection for coding-team hooks.

Both `coding-team-lifecycle.py` (PostToolUse second-opinion gate) and
`write-guard.py` (PreToolUse Phase 5 edit guard) ask the same question:
"is there a coding-team pipeline currently in progress?". The answer is
the most recent in-progress plan file under `$MAIN_ROOT/docs/plans/`.

A plan is "in-progress" when:
  - frontmatter does NOT match `^status:\\s*complete` (case-insensitive,
    multiline), AND
  - file mtime is within the last `PLAN_STALE_SECONDS` (4 hours).

`MAIN_ROOT` is the repository root containing `.git`, derived via
`git rev-parse --path-format=absolute --git-common-dir`. Worktrees and
the primary checkout resolve to the same root, so the same plan
directory is consulted from any worktree.
"""

import re
import subprocess
import time
from pathlib import Path

PLAN_STALE_SECONDS = 4 * 3600

_FRONTMATTER_COMPLETE_RE = re.compile(
    r"^status:\s*complete",
    re.MULTILINE | re.IGNORECASE,
)


def find_active_plan() -> Path | None:
    """Return the most recent in-progress plan file, or None.

    Plans are scanned newest-first by mtime; the first plan that is not
    marked complete and is not stale wins. If git is unavailable, the
    docs/plans directory does not exist, or no candidate qualifies,
    returns None.
    """
    try:
        raw = subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if not raw:
        return None
    # Strip trailing /.git (or worktree's literal `.git` suffix) to get repo root.
    if raw.endswith("/.git"):
        main_root = raw[: -len("/.git")]
    else:
        main_root = raw
    plans_dir = Path(main_root) / "docs" / "plans"
    if not plans_dir.exists():
        return None
    try:
        candidates = sorted(
            plans_dir.glob("*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None
    now = time.time()
    for plan in candidates:
        try:
            text = plan.read_text(errors="replace")[:500]
        except OSError:
            continue
        if _FRONTMATTER_COMPLETE_RE.search(text):
            continue
        try:
            mtime = plan.stat().st_mtime
        except OSError:
            continue
        if now - mtime > PLAN_STALE_SECONDS:
            continue
        return plan
    return None
