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

import hashlib
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


def _parse_frontmatter(
    text: str, preserve_case_keys: frozenset[str] = frozenset()
) -> dict[str, str]:
    """Parse YAML frontmatter delimited by leading '---' lines.

    Returns {} if no frontmatter or malformed. Strips a leading UTF-8 BOM.
    Only handles flat `key: value` lines (sufficient for our schema).
    Keys are always lowercased. Values are stripped of surrounding quotes and
    lowercased for case-insensitive comparison, EXCEPT for keys listed in
    `preserve_case_keys` — those keep their original case because they carry
    case-sensitive data (file paths such as `SKILL.md` / `CLAUDE.md`).
    Default is the empty set, so existing callers are unaffected.

    Raises AmbiguousActivePlanError if the same key (after lowercasing)
    appears more than once in one frontmatter block. A second `status:` or
    `instruction_files:` line would otherwise silently overwrite the first
    (last-write-wins) — unacceptable for keys that control gating and edit
    authorization decisions. This is the same "cannot determine which value
    is authoritative, refuse to guess" situation the class already models
    for multiple in-progress plans; callers must fail closed on it.
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
            key = m.group(1).lower()
            value = m.group(2).strip()
            # Strip matching surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
                value = value[1:-1]
            if key not in preserve_case_keys:
                value = value.lower()
            if key in out:
                raise AmbiguousActivePlanError(
                    f"duplicate frontmatter key {key!r} — cannot determine "
                    f"which value is authoritative, refusing to guess"
                )
            out[key] = value
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


# Allowlist, not deny-list (P1-B): a deny-list of GIT_* vars already failed
# once — GIT_DIR/GIT_WORK_TREE alone left GIT_COMMON_DIR and
# GIT_CEILING_DIRECTORIES open, both independently redirecting repo
# discovery (reproduced against the live hook: GIT_COMMON_DIR pointed at
# an unrelated empty repo's .git redirects plan_root there; setting
# GIT_CEILING_DIRECTORIES to the armed repo's own root makes git refuse to
# discover it at all, yielding (None, None) and hitting check_phase5's
# `plan_root is None` early return — fail OPEN). Git exposes far more
# GIT_*-prefixed variables than any deny-list can enumerate and stay
# current (GIT_DISCOVERY_ACROSS_FILESYSTEM, GIT_OBJECT_DIRECTORY,
# GIT_ALTERNATE_OBJECT_DIRECTORIES, GIT_INDEX_FILE, GIT_NAMESPACE, ...).
# Default-deny instead: strip EVERY environment variable whose name starts
# with "GIT_" from the discovery subprocess's env, except this explicit
# allowlist of vars confirmed to affect only editing/authoring/transport
# UI — never WHICH repository or working tree `git rev-parse` resolves to.
# An unrecognized GIT_* var is stripped by default (fail closed), not kept.
_GIT_ENV_ALLOWLIST = {
    "GIT_EDITOR",
    "GIT_PAGER",
    "GIT_ASKPASS",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "GIT_TERMINAL_PROMPT",
    "GIT_HTTP_LOW_SPEED_LIMIT",
    "GIT_HTTP_LOW_SPEED_TIME",
    "GIT_CURL_VERBOSE",
    "GIT_PROTOCOL",
    "GIT_MERGE_VERBOSITY",
    "GIT_FLUSH",
    "GIT_REFLOG_ACTION",
    "GIT_EXTERNAL_DIFF",
    "GIT_DIFF_OPTS",
    "GIT_SEQUENCE_EDITOR",
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_AUTHOR_DATE",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
    "GIT_COMMITTER_DATE",
    "GIT_TRACE",
    "GIT_TRACE_PACK_ACCESS",
    "GIT_TRACE_PACKET",
    "GIT_TRACE_PERFORMANCE",
    "GIT_TRACE_SETUP",
    # Not git's own var — this repo's git-safety-guard hook flag, which
    # merely happens to share the "GIT_" string prefix. Kept for
    # documentation only: this scrubbed dict is used SOLELY as the env for
    # the discovery subprocess below, never propagated to write-guard.py's
    # own process or any other hook, so its presence or absence here
    # cannot affect git-safety-guard.py's behavior either way.
    "GIT_SAFETY_ALLOW_COMPOUND",
}


def _scrub_git_env() -> dict:
    """Return a copy of the process env with every GIT_*-prefixed variable
    removed EXCEPT _GIT_ENV_ALLOWLIST above.

    Used only for the git-discovery subprocess env in
    _resolve_target_git_roots() below — never for write-guard.py's own
    process env or any other subprocess.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") or k in _GIT_ENV_ALLOWLIST
    }


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

    Every GIT_*-prefixed environment variable (except _GIT_ENV_ALLOWLIST)
    is scrubbed from the subprocess environment before invoking git — see
    _scrub_git_env() — so an ambient value pointing at an unrelated repo
    (GIT_DIR, GIT_WORK_TREE, GIT_COMMON_DIR, GIT_CEILING_DIRECTORIES, or
    any other discovery-affecting GIT_* var) cannot redirect discovery
    away from file_path's real owning repo.

    Returns (None, None) if file_path is not inside any git repository,
    file_path is not an ABSOLUTE path (P3-A — a relative path would make
    the ancestor walk below land on the PROCESS's cwd, reintroducing the
    exact cwd-scoped defect this function exists to close; not reachable
    through the real Edit/Write client, which always supplies absolute
    paths, but defended anyway), or on any resolution failure. Callers
    must treat all of these as "not pipeline-gated" and must NOT fall
    back to cwd-based resolution — that would reintroduce the exact
    defect this function exists to fix.

    Test seam: see _test_seam_root() — when active, both worktree_root and
    plan_root are the single overridden path (the test fixtures this seam
    supports are single-repo, so the two answers coincide).
    """
    seam = _test_seam_root()
    if seam is not None:
        return seam, seam

    try:
        target = Path(file_path)
        if not target.is_absolute():
            return None, None
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

    scrubbed_env = _scrub_git_env()
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
        try:
            fm = _parse_frontmatter(text[:4096])
        except AmbiguousActivePlanError as exc:
            # Re-raise naming the offending plan, matching the sibling
            # error paths below (unreadable plan / multiple in-progress),
            # which both name the file. Keep the original reason (duplicate
            # key detail) and exception type; add the path, don't replace it.
            raise AmbiguousActivePlanError(f"{exc} (plan: {plan})") from exc
        if fm.get("status") == "in-progress":
            in_progress.append(plan)

    if len(in_progress) > 1:
        raise AmbiguousActivePlanError(
            "multiple plans with status: in-progress: "
            + ", ".join(str(p) for p in in_progress)
        )
    return in_progress[0] if in_progress else None


# ---------------------------------------------------------------------------
# Plan-scoped instruction-file allowlist
# ---------------------------------------------------------------------------
#
# THREAT MODEL — read before changing anything below.
#
# This allowlist is PROCESS DISCIPLINE, not an adversarial security boundary.
# Its job is to stop Claude from editing behavioral instruction files that the
# reviewed plan never declared. It is NOT a defense against an attacker.
#
# The allowlist lives in the active plan file under `docs/plans/`, which is
# gitignored (`.gitignore:2`). Anyone (or anything) able to write that plan can
# authorize any path, and the change leaves no git audit trail. That is an
# ACCEPTED limitation for the actual threat model. Do NOT describe this
# mechanism as a security control anywhere in code, tests, or docs.
#
# The path checks below (reject absolute entries, reject entries that escape
# the repo root, compare structurally rather than by substring) exist to stop
# ACCIDENTS and typos — a declared `agents/x.md` must never silently authorize
# `evil/agents/x.md` or `agents/x.md.bak` — not to stop a determined attacker.

INSTRUCTION_ALLOWLIST_KEY = "instruction_files"


class MalformedInstructionAllowlistError(RuntimeError):
    """The active plan declares `instruction_files` but the value is unusable.

    Callers MUST fail closed and BLOCK the edit. Never treat this as "no
    allowlist declared" — that would turn a typo into a silent full allow.
    """


def read_instruction_allowlist(
    plan: Path, root: Path
) -> frozenset[Path] | None:
    """Return the instruction files the given plan authorizes editing.

    `root` is the repository root that CONTAINS `plan`, supplied by the
    caller. The reader does NOT re-derive it. Active-plan discovery has
    already resolved the root in order to find `plan` at all; deriving it a
    second time here would add a second `git rev-parse` that can fail
    independently, and could bind entries to a different root than the one
    the plan was found under.

    Returns None when the plan declares no `instruction_files` key. Callers
    MUST treat None as "nothing is authorized" and block every
    instruction-file edit — that is the pre-allowlist behavior and it must
    not regress into an allow.

    Returns a frozenset of RESOLVED ABSOLUTE paths otherwise. Comparison at
    the call site is therefore plain `Path` equality on resolved paths, never
    a substring or prefix test (case study #35).

    Raises MalformedInstructionAllowlistError when the key is present but
    unusable: unreadable plan, empty value, an EMPTY ENTRY (leading,
    trailing, or doubled comma), an absolute entry, an entry that resolves
    outside the repo root, a duplicate `instruction_files` key in the plan's
    own frontmatter, or a root that is not an existing directory. Callers
    MUST fail closed on this and BLOCK.
    """
    try:
        text = plan.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError) as exc:
        raise MalformedInstructionAllowlistError(
            f"unreadable plan {plan}: {exc}"
        ) from exc

    try:
        fm = _parse_frontmatter(
            text[:4096], preserve_case_keys=frozenset({INSTRUCTION_ALLOWLIST_KEY})
        )
    except AmbiguousActivePlanError as exc:
        # Translate: this function's documented contract is to raise only
        # MalformedInstructionAllowlistError. A duplicate key is exactly as
        # unusable as any other malformed declaration below — fail closed.
        raise MalformedInstructionAllowlistError(
            f"`{INSTRUCTION_ALLOWLIST_KEY}` in {plan} has a duplicate "
            f"frontmatter key: {exc}"
        ) from exc
    raw = fm.get(INSTRUCTION_ALLOWLIST_KEY)
    if raw is None:
        return None

    # `str.split(",")` always returns at least one element, so `all()` alone
    # is the whole check: it is False iff some entry is empty, which covers
    # both an empty value and a leading/trailing/doubled comma.
    entries = [e.strip() for e in raw.split(",")]
    if not all(entries):
        raise MalformedInstructionAllowlistError(
            f"`{INSTRUCTION_ALLOWLIST_KEY}` in {plan} is malformed — it "
            f"declares no paths, or has an empty entry from a leading, "
            f"trailing, or doubled comma. Remove the key, or list at least "
            f"one repo-relative path with no empty entries. A malformed "
            f"declaration is NEVER silently normalized into a valid one: "
            f"`a.md,,b.md` is a typo, and quietly honouring `a.md` and `b.md` "
            f"would authorize an edit the author did not clearly declare."
        )

    try:
        root = root.resolve()
    except (OSError, ValueError) as exc:
        raise MalformedInstructionAllowlistError(
            f"cannot resolve repository root {root}: {exc}"
        ) from exc
    if not root.is_dir():
        raise MalformedInstructionAllowlistError(
            f"repository root {root} is not an existing directory — refusing "
            f"to evaluate `{INSTRUCTION_ALLOWLIST_KEY}`"
        )

    allowed: set[Path] = set()
    for entry in entries:
        candidate = Path(entry)
        if candidate.is_absolute():
            raise MalformedInstructionAllowlistError(
                f"`{INSTRUCTION_ALLOWLIST_KEY}` entries must be repo-relative; "
                f"got an absolute path: {entry}"
            )
        try:
            resolved = (root / candidate).resolve()
        except (OSError, ValueError) as exc:
            raise MalformedInstructionAllowlistError(
                f"cannot resolve `{INSTRUCTION_ALLOWLIST_KEY}` entry "
                f"{entry!r}: {exc}"
            ) from exc
        if not resolved.is_relative_to(root):
            raise MalformedInstructionAllowlistError(
                f"`{INSTRUCTION_ALLOWLIST_KEY}` entry escapes the repository "
                f"root: {entry!r}"
            )
        allowed.add(resolved)
    return frozenset(allowed)


# ---------------------------------------------------------------------------
# Cross-invocation persistent cache
# ---------------------------------------------------------------------------

def _cache_file_path(plan_root: "Path | None" = None) -> Path:
    """Return the path for the persistent active-plan cache file.

    The path is overridable via ACTIVE_PLAN_CACHE_FILE (used in tests) —
    the override always wins and is NOT further keyed by plan_root.

    Otherwise (P3-B), the filename is keyed by a hash of `plan_root`: a
    single fixed filename would be shared by every repo AND by both
    resolution modes (process-scoped `_git_main_root()` for
    coding-team-lifecycle.py vs. target-scoped `_resolve_target_git_roots()`
    for write-guard.py), since the cache entry holds only ONE result at a
    time and each write overwrites the whole file. Alternating lookups
    across repos (or across the two resolution modes) would then evict
    each other's entry on every call — a near-0% hit rate, plus a stat+scan
    per repo on every hook invocation (still fail-safe: correctness is
    unaffected, since `repo_root` is also checked in the hit condition; the
    entry would just always miss and be recomputed). Hashing plan_root
    into the filename gives each repo its own cache file, so alternating
    between repos no longer evicts either one.
    """
    override = os.environ.get("ACTIVE_PLAN_CACHE_FILE")
    if override:
        return Path(override)
    if plan_root is not None:
        digest = hashlib.sha256(str(plan_root).encode("utf-8")).hexdigest()[:16]
        return Path(tempfile.gettempdir()) / f"coding-team-active-plan-cache-{digest}.json"
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


# Bumped whenever the cache entry SHAPE or validation rules change in a way
# that makes an old entry unsafe to trust (P1-4: entries written before a
# None result stopped being cached could still hold a stale negative
# result). A reader rejects any entry missing this field, or whose value
# doesn't match — see the version check in find_active_plan_cached() below.
_CACHE_ENTRY_VERSION = 2


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
    The TTL is a backstop only — the signature is the primary invalidator.
    IMPORTANT: this is NOT airtight — an in-place content flip (e.g.
    status: planned -> in-progress) that also restores the ORIGINAL mtime
    (via os.utime) is invisible to the signature. Creation, deletion, and
    rename of plan files ARE always caught, since the candidate list itself
    changes. A None result is therefore never cached (see below), so the
    worst case of the signature's blind spot is a needless rescan, not a
    stale disarm.

    A None result (no active plan) is NEVER cached (P1-4) — it is the
    DISARMED answer, and caching it risks serving a stale None while a
    plan is actually armed (exactly the mtime-preserving flip above).
    Caching only positive results means the worst stale-cache outcome is
    an extra scan, not a silent bypass. Measured: an uncached scan of 38
    real plan files costs ~1.2ms — negligible next to hook subprocess
    launch (~12ms for the git call alone). Every entry also carries a
    version field (_CACHE_ENTRY_VERSION); a reader rejects an entry
    missing it or bearing a different one, so a pre-existing cache file
    written before this fix (which could hold a stale negative result)
    is never trusted. A `plan_path` that is falsey (None/"" — a
    hand-written or externally-produced entry, since ACTIVE_PLAN_CACHE_FILE
    lets anything choose where this file lives) is likewise treated as a
    cache MISS on read, not as a cached None; and an entry whose `ts` is
    ahead of `now` is rejected outright (the naive `now - ts < ttl_seconds`
    check alone accepts a future ts, since the subtraction goes negative).

    Stale POSITIVE results are a separate, narrower, and currently
    out-of-scope hole: if plan A is cached in-progress and plan B is then
    flipped to in-progress with A's plan.md untouched (candidate list and
    A's own signature entry unchanged), a cache hit still returns A while
    the authoritative uncached call would raise AmbiguousActivePlanError.
    Today this still fails closed (either path blocks the gate), but it
    MISIDENTIFIES the arming plan — a hole against any future feature that
    attaches per-file authority to the specific plan path returned.

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

    cache_path = _cache_file_path(plan_root)
    now = time.time()

    # Attempt to read and validate the cache
    try:
        raw = cache_path.read_text(encoding="utf-8")
        entry = json.loads(raw)
        entry_ts = float(entry.get("ts", 0))
        stored_plan_path = entry.get("plan_path")

        if (
            entry.get("version") == _CACHE_ENTRY_VERSION
            and entry.get("repo_root") == str(plan_root)
            and entry.get("session_id") == session_id
            and entry.get("signature") == current_sig
            and stored_plan_path  # falsey (None/""/missing) -> cache MISS, not a cached None
            and entry_ts <= now  # reject a future-dated ts (would never expire)
            and (now - entry_ts) < ttl_seconds
        ):
            # Cache hit: return the stored result
            return Path(stored_plan_path)
    except (OSError, ValueError, json.JSONDecodeError, TypeError, KeyError):
        # Cache miss or corrupt — proceed to rescan
        pass

    # Cache miss: call the authoritative primitive, passing plan_root through
    # rather than re-deriving it (avoids a second git invocation when the
    # caller already resolved it via _resolve_target_git_roots()).
    # AmbiguousActivePlanError is intentionally NOT caught — let it propagate.
    result = find_active_plan(plan_root=plan_root)

    # Write the new cache entry, ignoring write errors (cache is optional).
    # Only when a plan was actually found — a None result must never be
    # written (P1-4): it is the DISARMED answer, and caching it risks
    # serving a stale None on a later call while a plan is actually armed.
    if result is not None:
        try:
            entry = {
                "version": _CACHE_ENTRY_VERSION,
                "repo_root": str(plan_root),
                "session_id": session_id,
                "signature": current_sig,
                "plan_path": str(result),
                "ts": now,
            }
            cache_path.write_text(json.dumps(entry), encoding="utf-8")
        except OSError:
            pass

    return result
