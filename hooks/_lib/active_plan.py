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

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# TEMP DIAGNOSTIC (task #12 CI investigation — remove once the runner-side
# root cause is confirmed): gated by ACTIVE_PLAN_DEBUG=1, prints internal
# active-plan-resolution state to stderr so it surfaces in CI logs.
_DEBUG = os.environ.get("ACTIVE_PLAN_DEBUG") == "1"


def _debug(msg: str) -> None:
    if _DEBUG:
        print(f"[active_plan debug] {msg}", file=sys.stderr, flush=True)


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
    """Return the absolute repository root, or None if not in a git repo.

    Test seam: if CODING_TEAM_MAIN_ROOT is set and non-empty, it is returned
    directly and `git` is never invoked. This lets tests point at a tmp repo
    without depending on `git rev-parse` succeeding in ephemeral CI sandboxes
    (git resolution can fail silently inside a fresh pytest tmp_path repo).
    Unset (the default / production path): behavior is unchanged, git is
    always consulted.
    """
    override = os.environ.get("CODING_TEAM_MAIN_ROOT")
    _debug(f"cwd={os.getcwd()!r} CODING_TEAM_MAIN_ROOT={override!r}")
    if override:
        _debug(f"using override root: {override!r}")
        return Path(override)
    try:
        raw = subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        _debug(f"git rev-parse failed: {exc!r}")
        return None
    _debug(f"git rev-parse raw={raw!r}")
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
    _debug(f"main_root={main_root!r}")
    if main_root is None:
        return None
    plans_dir = main_root / "docs" / "plans"
    _debug(f"plans_dir={plans_dir!r} is_dir={plans_dir.is_dir()!r}")
    if not plans_dir.is_dir():
        return None
    try:
        candidates = sorted(plans_dir.glob("*.md"))
    except OSError as exc:
        raise AmbiguousActivePlanError(f"plans dir unlistable: {exc}") from exc
    _debug(f"candidates={[str(p) for p in candidates]!r}")

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


# ---------------------------------------------------------------------------
# Cross-invocation persistent cache
# ---------------------------------------------------------------------------

def _cache_file_path() -> Path:
    """Return the path for the persistent active-plan cache file.

    The path is overridable via ACTIVE_PLAN_CACHE_FILE (used in tests).
    Defaults to a fixed name in the system temp directory.
    """
    override = os.environ.get("ACTIVE_PLAN_CACHE_FILE")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "coding-team-active-plan-cache.json"


def _compute_signature(candidates: list[Path]) -> list[list]:
    """Return a JSON-serialisable signature for the given candidate paths.

    The signature is the sorted list of [str(path), st_mtime_ns] pairs.
    stat-ing every candidate is cheap; what we avoid is reading + YAML-
    parsing each file's content on every hook invocation.

    If any candidate cannot be stat-ed, raise OSError so the caller treats
    the cache as invalid and falls through to find_active_plan().
    """
    pairs: list[list] = []
    for p in candidates:
        pairs.append([str(p), p.stat().st_mtime_ns])
    pairs.sort(key=lambda x: x[0])
    return pairs


def find_active_plan_cached(ttl_seconds: int = 5) -> "Path | None":
    """Return the unique in-progress plan, using a file-backed cache.

    Cache is keyed by repo_root + session_id and is invalidated when any
    candidate plan file's st_mtime_ns changes (file-signature invalidation).
    The TTL is a backstop only — the signature is the primary invalidator,
    so an in-place status flip (which changes st_mtime_ns) immediately breaks
    the signature and forces a fresh read on the very next call.

    AmbiguousActivePlanError is NEVER cached — it propagates every time.
    On any cache I/O or stat error, falls through to find_active_plan().

    The cache file path can be overridden via the ACTIVE_PLAN_CACHE_FILE
    environment variable (used in tests).
    """
    # Resolve repo root and session id before touching the cache
    try:
        main_root = _git_main_root()
    except (OSError, subprocess.SubprocessError):
        # If we can't resolve root, skip cache entirely
        return find_active_plan()

    if main_root is None:
        return find_active_plan()

    try:
        from _lib.state import get_session_id
    except ImportError:
        # _lib.state unavailable — skip cache
        return find_active_plan()

    session_id = get_session_id()
    plans_dir = main_root / "docs" / "plans"

    # Collect candidates and compute current signature.
    # If plans_dir doesn't exist, there are no candidates — signature is [].
    try:
        if plans_dir.is_dir():
            candidates = sorted(plans_dir.glob("*.md"))
        else:
            candidates = []
        current_sig = _compute_signature(candidates)
    except OSError:
        # Can't stat candidates — fall through to uncached
        return find_active_plan()

    cache_path = _cache_file_path()
    now = time.time()
    _debug(
        f"cache_path={cache_path!r} main_root={main_root!r} session_id={session_id!r} "
        f"current_sig={current_sig!r}"
    )

    # Attempt to read and validate the cache
    try:
        raw = cache_path.read_text(encoding="utf-8")
        entry = json.loads(raw)
        _debug(f"cache entry read: {entry!r}")

        if (
            entry.get("repo_root") == str(main_root)
            and entry.get("session_id") == session_id
            and entry.get("signature") == current_sig
            and (now - float(entry.get("ts", 0))) < ttl_seconds
        ):
            # Cache hit: return the stored result
            stored = entry.get("plan_path")
            _debug(f"cache HIT -> plan_path={stored!r}")
            return Path(stored) if stored else None
        _debug("cache present but did not match (repo_root/session_id/signature/ttl)")
    except (OSError, ValueError, json.JSONDecodeError, TypeError, KeyError) as exc:
        # Cache miss or corrupt — proceed to rescan
        _debug(f"cache read failed/absent: {exc!r}")

    # Cache miss: call the authoritative primitive.
    # AmbiguousActivePlanError is intentionally NOT caught — let it propagate.
    result = find_active_plan()
    _debug(f"cache MISS -> find_active_plan() result={result!r}")

    # Write the new cache entry, ignoring write errors (cache is optional).
    try:
        entry = {
            "repo_root": str(main_root),
            "session_id": session_id,
            "signature": current_sig,
            "plan_path": str(result) if result is not None else None,
            "ts": now,
        }
        cache_path.write_text(json.dumps(entry), encoding="utf-8")
    except OSError:
        pass

    return result
