"""Shared active-plan detection for coding-team hooks.

Both `coding-team-lifecycle.py` (PostToolUse second-opinion gate) and
`write-guard.py` (PreToolUse Phase 5 edit guard) ask the same question:
"is there a coding-team pipeline currently in progress?". The answer is
the unique plan file under `$MAIN_ROOT/docs/plans/` whose YAML
frontmatter declares `status: in-progress`.

Status semantics:
  - `status: planned`     — drafted but not yet executing; gate dormant
  - `status: in-progress` — pipeline active; gate fires
  - `status: complete`    — pipeline done; gate dormant
  - missing/no frontmatter — no gate (back-compat for non-pipeline plans)

The orchestrator owns these transitions: planned -> in-progress at
Phase 5 entry, in-progress -> complete at Phase 6 end. mtime is no
longer consulted; lifetime is determined by frontmatter.

Failure policy:
  - 0 in-progress plans -> return None (no gate)
  - 1 in-progress plan  -> return that Path
  - >1 in-progress plans -> raise AmbiguousActivePlanError (callers fail closed)
  - unreadable plan      -> raise AmbiguousActivePlanError (callers fail closed)

`MAIN_ROOT` is the repository root containing `.git`, derived via
`git rev-parse --path-format=absolute --git-common-dir`. Worktrees and
the primary checkout resolve to the same root, so the same plan
directory is consulted from any worktree.
"""

import re
import subprocess
from pathlib import Path


class AmbiguousActivePlanError(RuntimeError):
    """Multiple plans claim status: in-progress, or a candidate plan is
    unreadable. Hook callers must fail closed and block with the message.
    """


_FRONTMATTER_KEY_RE = re.compile(r"^([a-zA-Z_][\w-]*)\s*:\s*(.*?)\s*$")
_FRONTMATTER_END_RE = re.compile(r"^---\s*$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML frontmatter delimited by leading '---' lines.

    Returns {} if no frontmatter or malformed. Strips a leading UTF-8 BOM.
    Only handles flat `key: value` lines (sufficient for our schema).
    Keys are lowercased; values are stripped of surrounding quotes and
    lowercased for case-insensitive comparison.
    """
    # Strip UTF-8 BOM if present
    if text.startswith("﻿"):
        text = text[1:]
    if not (text.startswith("---\n") or text.startswith("---\r\n")):
        return {}
    # Skip past the opening delimiter
    rest = text[4:] if text.startswith("---\n") else text[5:]
    end = _FRONTMATTER_END_RE.search(rest)
    if not end:
        return {}
    body = rest[: end.start()]
    out: dict[str, str] = {}
    for line in body.splitlines():
        m = _FRONTMATTER_KEY_RE.match(line)
        if m:
            value = m.group(2).strip()
            # Strip matching surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
                value = value[1:-1]
            out[m.group(1).lower()] = value.strip().lower()
    return out


def _git_main_root() -> Path | None:
    """Return the absolute repository root, or None if not in a git repo."""
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
        return Path(raw[: -len("/.git")])
    return Path(raw)


def find_active_plan() -> Path | None:
    """Return the unique in-progress plan, or None.

    Raises AmbiguousActivePlanError if multiple plans claim
    `status: in-progress` (orchestrator must mark exactly one) or if a
    plan exists but cannot be read. Callers should treat this as
    "fail closed": block with the error message.
    """
    main_root = _git_main_root()
    if main_root is None:
        return None
    plans_dir = main_root / "docs" / "plans"
    if not plans_dir.is_dir():
        return None
    try:
        candidates = sorted(plans_dir.glob("*.md"))
    except OSError as exc:
        raise AmbiguousActivePlanError(f"plans dir unlistable: {exc}") from exc

    in_progress: list[Path] = []
    for plan in candidates:
        try:
            text = plan.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            # Fail closed: an unreadable plan could be the in-progress one.
            raise AmbiguousActivePlanError(
                f"unreadable plan: {plan} ({exc})"
            ) from exc
        # Frontmatter must be near top — only inspect first 4096 chars
        fm = _parse_frontmatter(text[:4096])
        if fm.get("status") == "in-progress":
            in_progress.append(plan)

    if len(in_progress) > 1:
        raise AmbiguousActivePlanError(
            "multiple plans with status: in-progress: "
            + ", ".join(str(p) for p in in_progress)
        )
    return in_progress[0] if in_progress else None
