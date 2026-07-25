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

`MAIN_ROOT` (a.k.a. `plan_root`) is the repository root containing `.git`,
derived via `git rev-parse --path-format=absolute --git-common-dir`.
Worktrees and the primary checkout resolve to the same root, so the same
plan directory is consulted from any worktree — this holds under BOTH
resolution modes below, since both call the identical `--git-common-dir`
mechanism; only the starting directory differs.

Two resolution modes populate `plan_root`:
  - Process-scoped (`_git_main_root()`): answers "what repo is the
    CURRENT PROCESS in?" via `git rev-parse` from cwd. Used by callers
    with no specific target file (e.g. coding-team-lifecycle.py's
    PostToolUse hook, which also fires on non-Edit/Write tools). Must
    NOT be used for a per-file gate decision — relocating cwd changes
    the answer without changing which file is being edited.
  - Target-scoped (`_resolve_target_git_roots()`): answers "what repo
    OWNS this file?" via `git rev-parse` from the file's own (nearest
    existing) directory, with GIT_DIR/GIT_WORK_TREE scrubbed. Used by
    write-guard.py's Phase 5 edit gate (see check_phase5), which must
    follow the edited file regardless of the process's cwd.
"""

import json
import os
import re
import subprocess
import tempfile
import time
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


def _test_seam_root() -> Path | None:
    """Return the CODING_TEAM_MAIN_ROOT override iff paired with a truthy
    CODING_TEAM_TEST_SEAM, else None.

    Centralized so both the process-scoped and target-scoped resolvers
    honor the identical paired-sentinel contract. The pairing exists so an
    ambient/leftover CODING_TEAM_MAIN_ROOT (e.g. from a prior test run's
    exported env, or a stray shell export) cannot silently override real
    git discovery in production — a test that wants the override must set
    BOTH vars explicitly. CODING_TEAM_TEST_SEAM is checked for truthiness
    (not merely "set"): a caller that explicitly sets it to "" is
    deliberately disabling the seam for that one invocation.
    """
    override = os.environ.get("CODING_TEAM_MAIN_ROOT")
    if override and os.environ.get("CODING_TEAM_TEST_SEAM"):
        return Path(override)
    return None


def _git_main_root() -> Path | None:
    """Return the absolute repository root for the CURRENT PROCESS, or None.

    PROCESS-scoped: answers "what repo is this process's cwd in?" via
    `git rev-parse` run with no `-C`, so it follows the process's cwd. Do
    NOT use this for a per-file gate decision — see _resolve_target_git_roots()
    for the target-scoped equivalent write-guard.py's Phase 5 edit gate uses
    instead. This function remains the right choice for callers with no
    specific target file (e.g. coding-team-lifecycle.py's PostToolUse hook).

    Test seam: see _test_seam_root() — CODING_TEAM_MAIN_ROOT is honored only
    when paired with a truthy CODING_TEAM_TEST_SEAM; otherwise git is always
    consulted (production behavior, unchanged).
    """
    seam = _test_seam_root()
    if seam is not None:
        return seam
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


_GIT_ENV_SCRUB_KEYS = ("GIT_DIR", "GIT_WORK_TREE")


def _resolve_target_git_roots(file_path: str) -> "tuple[Path | None, Path | None]":
    """Resolve (worktree_root, plan_root) for the repo that OWNS file_path.

    TARGET-scoped: git discovery runs with `-C <nearest existing ancestor of
    file_path>`, never from the process's cwd — so relocating the process's
    working directory cannot change the answer, which is the defect this
    function exists to close (P1-5). `file_path` may not exist yet (a Write
    to a new file), so discovery starts from the nearest existing ancestor
    directory rather than file_path itself.

    Returns two DIFFERENT answers from one `git rev-parse` call:
      - worktree_root (`--show-toplevel`): the physical checkout file_path
        lives in. A linked worktree has its own worktree_root, distinct
        from the main checkout's.
      - plan_root (`--git-common-dir`, `/.git` suffix stripped): the root
        shared by every worktree of the same repo — this is what preserves
        the worktree contract (module docstring above): docs/plans/ lives
        only in the main checkout, but every worktree's plan_root resolves
        to it.

    GIT_DIR and GIT_WORK_TREE are scrubbed from the subprocess environment
    before invoking git, so ambient values pointing at an unrelated repo
    cannot redirect discovery away from file_path's real owning repo.

    Returns (None, None) if file_path is not inside any git repository, or
    on any resolution failure. Callers must treat that as "not
    pipeline-gated" and must NOT fall back to cwd-based resolution — that
    would reintroduce the exact defect this function exists to fix.

    Test seam: see _test_seam_root() — when active, both worktree_root and
    plan_root are the single overridden path (the test fixtures this seam
    supports are single-repo, so the two answers coincide).
    """
    seam = _test_seam_root()
    if seam is not None:
        return seam, seam

    try:
        target = Path(file_path)
        start = target
        while not start.exists():
            parent = start.parent
            if parent == start:
                # Reached filesystem root without finding an existing
                # ancestor — nothing to run `git -C` against.
                return None, None
            start = parent
        if not start.is_dir():
            start = start.parent
    except (OSError, ValueError):
        return None, None

    scrubbed_env = {
        k: v for k, v in os.environ.items() if k not in _GIT_ENV_SCRUB_KEYS
    }
    try:
        raw = subprocess.check_output(
            [
                "git",
                "-C",
                str(start),
                "rev-parse",
                "--path-format=absolute",
                "--show-toplevel",
                "--git-common-dir",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            env=scrubbed_env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None, None

    lines = raw.strip("\n").split("\n")
    if len(lines) != 2 or not lines[0] or not lines[1]:
        return None, None
    toplevel_raw, common_dir_raw = lines

    worktree_root = Path(toplevel_raw)
    plan_root = (
        Path(common_dir_raw[: -len("/.git")])
        if common_dir_raw.endswith("/.git")
        else Path(common_dir_raw)
    )
    return worktree_root, plan_root


_UNSET = object()  # sentinel: "plan_root not supplied" vs. explicit None


def find_active_plan(*, plan_root: "Path | None" = _UNSET) -> Path | None:  # type: ignore[assignment]
    """Return the unique in-progress plan, or None.

    `plan_root`: repo root under which to look for docs/plans/. Omitted (the
    default `_UNSET` sentinel) falls back to the PROCESS-scoped
    `_git_main_root()` — this default exists only for callers with no
    specific target file (e.g. coding-team-lifecycle.py). Callers gating a
    specific file edit (write-guard.py's check_phase5) MUST resolve
    plan_root from that file via `_resolve_target_git_roots()` and pass it
    explicitly — see the module docstring's "Two resolution modes". Passing
    `plan_root=None` explicitly means "no owning repo for this target" and
    returns None immediately (no gate), same as a repo with no docs/plans/.

    Raises AmbiguousActivePlanError if multiple plans claim
    `status: in-progress` (orchestrator must mark exactly one) or if a
    plan exists but cannot be read. Callers should treat this as
    "fail closed": block with the error message.
    """
    if plan_root is _UNSET:
        plan_root = _git_main_root()
    if plan_root is None:
        return None
    plans_dir = plan_root / "docs" / "plans"
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


def find_active_plan_cached(
    ttl_seconds: int = 5, *, plan_root: "Path | None" = _UNSET  # type: ignore[assignment]
) -> "Path | None":
    """Return the unique in-progress plan, using a file-backed cache.

    `plan_root` semantics are identical to `find_active_plan()`'s (see its
    docstring): omitted falls back to PROCESS-scoped `_git_main_root()`;
    an explicit value (including explicit None) is used as-is and is NOT
    re-resolved. Target-scoped callers (write-guard.py) should resolve
    plan_root once via `_resolve_target_git_roots()` and pass it here —
    passing it explicitly also skips a redundant `_git_main_root()` call
    on the cache-miss path below.

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
    if plan_root is _UNSET:
        try:
            plan_root = _git_main_root()
        except (OSError, subprocess.SubprocessError):
            # If we can't resolve root, skip cache entirely
            return find_active_plan()

    if plan_root is None:
        return find_active_plan(plan_root=None)

    try:
        from _lib.state import get_session_id
    except ImportError:
        # _lib.state unavailable — skip cache
        return find_active_plan(plan_root=plan_root)

    session_id = get_session_id()
    plans_dir = plan_root / "docs" / "plans"

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
        return find_active_plan(plan_root=plan_root)

    cache_path = _cache_file_path()
    now = time.time()

    # Attempt to read and validate the cache
    try:
        raw = cache_path.read_text(encoding="utf-8")
        entry = json.loads(raw)

        if (
            entry.get("repo_root") == str(plan_root)
            and entry.get("session_id") == session_id
            and entry.get("signature") == current_sig
            and (now - float(entry.get("ts", 0))) < ttl_seconds
        ):
            # Cache hit: return the stored result
            stored = entry.get("plan_path")
            return Path(stored) if stored else None
    except (OSError, ValueError, json.JSONDecodeError, TypeError, KeyError):
        # Cache miss or corrupt — proceed to rescan
        pass

    # Cache miss: call the authoritative primitive, passing plan_root through
    # rather than re-deriving it (avoids a second git invocation when the
    # caller already resolved it via _resolve_target_git_roots()).
    # AmbiguousActivePlanError is intentionally NOT caught — let it propagate.
    result = find_active_plan(plan_root=plan_root)

    # Write the new cache entry, ignoring write errors (cache is optional).
    try:
        entry = {
            "repo_root": str(plan_root),
            "session_id": session_id,
            "signature": current_sig,
            "plan_path": str(result) if result is not None else None,
            "ts": now,
        }
        cache_path.write_text(json.dumps(entry), encoding="utf-8")
    except OSError:
        pass

    return result
