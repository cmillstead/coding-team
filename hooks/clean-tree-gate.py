#!/usr/bin/env python3
"""Clean-tree completion guard (PreToolUse, Edit|Write).

Fires ONLY when an Edit/Write to a `docs/plans/*.md` file transitions the plan
frontmatter `status: in-progress` -> `status: complete` — the coding-team
finish line (phases/completion.md step 7). On that transition, runs
`git status --porcelain` in the repo that OWNS the plan file, EXCLUDING the
plan file itself, and BLOCKs if anything else is uncommitted/untracked.

Design contract: the dispatcher isolates handler exceptions and FAILS OPEN, so
this guard must reach an EXPLICIT allow (bare return) or deny (_output.block)
on the completion path — it never relies on crashing to block. On ANY
uncertainty (not a repo, git error, unparseable edit, non-transition,
non-plan-file), it ALLOWS. The only escape hatch is a clean tree: commit or
discard. There is NO override env var.

Root resolution is TARGET-scoped (the plan file's own git identity via
_resolve_target_git_roots), never the process cwd — mirroring
write-guard.check_phase5's P1-5 fix.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path

from _lib import event as _event
from _lib import output as _output
from _lib.active_plan import (
    AmbiguousActivePlanError,
    _parse_frontmatter,
    _resolve_target_git_roots,
    _scrub_git_env,
)


def _plan_status(text: str) -> "str | None":
    """Return the frontmatter `status`, or None. Never raises.

    Passes the FULL text (FIX 1 — a `[:4096]` slice could truncate a long
    frontmatter, e.g. a big `instruction_files:` list, so the closing `---`
    falls past the slice and the block parses as no-frontmatter -> status None
    -> not-a-transition -> a dirty completion would LEAK). `_parse_frontmatter`
    stops at the closing `---`, so passing the full text is safe and cheap.
    """
    try:
        fm = _parse_frontmatter(text)
    except AmbiguousActivePlanError:
        return None
    return fm.get("status")


def _is_plan_file(file_path: str, worktree_root: Path) -> bool:
    """True iff file_path is a direct child of <worktree_root>/docs/plans/ ending .md.

    Structural Path equality on resolved paths (never substring/startswith), so
    a nested docs/plans/<subdir>/x.md does NOT match.
    """
    try:
        target = Path(file_path)
        plans_dir = (worktree_root / "docs" / "plans").resolve()
        return target.resolve().parent == plans_dir and target.suffix == ".md"
    except (OSError, ValueError, RuntimeError):
        return False


def _post_edit_content(tool_name: str, tool_input: dict, pre: str) -> "str | None":
    """Reconstruct the plan text AFTER this edit from the ALREADY-READ pre-edit
    text `pre`, or None on any uncertainty.

    Write uses `content` (ignores `pre`); Edit applies old->new to `pre`
    (honoring replace_all). FIX 3: it applies to `pre` — the SAME snapshot the
    caller read for the PRE status — NOT a fresh disk read, so a concurrent
    write between the two reads cannot desync PRE and POST. Non-str inputs ->
    None (uncertainty -> caller allows).
    """
    if tool_name == "Write":
        content = tool_input.get("content", "")
        return content if isinstance(content, str) else None
    old = tool_input.get("old_string", "")
    new = tool_input.get("new_string", "")
    if not isinstance(old, str) or not isinstance(new, str):
        return None
    if tool_input.get("replace_all"):
        return pre.replace(old, new)
    return pre.replace(old, new, 1)


def _is_completion_transition(tool_name: str, tool_input: dict, target: Path) -> bool:
    """True iff PRE status is in-progress AND POST status is complete.

    PRE is read from disk ONCE; POST is reconstructed from that SAME `pre`
    string (FIX 3 — no second disk read, so a concurrent write cannot desync
    PRE/POST). A brand-new file that does not exist yet reads as unreadable ->
    False -> not a transition -> allow. Never raises.
    """
    try:
        pre = target.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return False
    if _plan_status(pre) != "in-progress":
        return False
    post = _post_edit_content(tool_name, tool_input, pre)
    if post is None:
        return False
    return _plan_status(post) == "complete"


def _is_rename_or_copy(xy: str) -> bool:
    """True iff the 2-char porcelain status code marks a rename or copy — an
    `R`/`C` in EITHER column (Codex P1).

    A STAGED rename is `R ` (R in the index column X); a WORKING-TREE rename is
    ` R` (R in the worktree column Y — e.g. after `git add -N` on the dest). Both
    are emitted by `git status --porcelain -z` as a TWO-path record
    (`XY <dest>\\0<orig>\\0`). Checking only the first column (the old `xy[0]`
    test) misses ` R`/` C`: the parser then fails to consume the orig field
    (mis-aligning every following entry) AND the callers treat the rename as an
    ordinary path — so a rename whose dest+orig are both baselined would be
    subtracted, leaking an uncommitted rename past completion. No non-rename
    status code (`??`, ` M`, `A `, `MM`, merge codes `UU`/`AA`/`DD`/… ) contains
    R or C, so membership over the 2-char field is exact.
    """
    return "R" in xy[:2] or "C" in xy[:2]


def _parse_porcelain_z(stream: bytes) -> "list[tuple[str, str, str]]":
    """Parse `git status --porcelain -z` BYTES into (xy, path, src) entries.

    Byte-based (FIX 9): the caller reads git stdout as raw bytes (no text=True),
    so a filename undecodable in the active locale cannot raise
    UnicodeDecodeError and escape to the top-level fail-open handler. Each field
    is decoded with `errors="surrogateescape"` — lossless and reversible, and it
    matches how `str(Path)` (via os.fsdecode) renders `plan_rel`, so the path
    comparison at the call site stays exact for any byte sequence.

    In `-z` form each entry is `XY <path>\\0` — 2 status chars, a space, the
    path, then a NUL terminator. Paths are NEVER quoted or escaped in `-z`
    (unlike porcelain v1, which quotes any path containing a space/quote/
    backslash regardless of core.quotepath). A rename/copy entry (status code
    with `R`/`C` in EITHER column — a staged `R ` or a worktree ` R`) is TWO NUL
    fields: `XY <dest>\\0<src>\\0` — the dest first (the `-z` ordering is
    dest-then-source), then the source, which we consume but do not return.
    Returns (xy, path) with `path` the primary/dest path. Consuming the second
    field is gated on `_is_rename_or_copy` (BOTH columns, Codex P1); a
    first-column-only test dropped a ` R`/` C` orig field and mis-aligned every
    following entry.
    """
    fields = stream.split(b"\0")
    entries: list[tuple[str, str, str]] = []
    i = 0
    while i < len(fields):
        field = fields[i]
        if not field:
            i += 1
            continue
        xy = field[:2].decode("ascii", errors="replace")
        path = field[3:].decode("utf-8", errors="surrogateescape")  # skip XY + space
        # A rename/copy record carries a second NUL field (the source path) —
        # R/C in EITHER column marks it (Codex P1). The source is RETURNED (as the
        # 3rd tuple element) so the baseline can record a rename's full identity
        # (status, dest, source) and grandfather an UNCHANGED pre-existing rename
        # without subtracting a NEW one (Codex round-3 FIX 1). Non-rename entries
        # carry src="".
        if _is_rename_or_copy(xy):
            src = (fields[i + 1].decode("utf-8", errors="surrogateescape")
                   if i + 1 < len(fields) else "")
            entries.append((xy, path, src))
            i += 2
        else:
            entries.append((xy, path, ""))
            i += 1
    return entries


def _parse_worktree_list_z(stream: bytes) -> "list[Path]":
    """Parse `git worktree list --porcelain -z` BYTES into worktree paths.

    FIX B (newline-safe): the plain `--porcelain` form is newline-delimited, but
    git permits a worktree path containing a newline and emits it RAW — so a
    `\\n`-split truncates such a path (its worktree's status then fails/skips and
    its dirt goes invisible → leak; a truncated prefix could also resolve to a
    different repo → false block). The `-z` form is NUL-delimited and never
    quotes or escapes, so it is unambiguous for ANY byte sequence.

    In `-z` form each worktree record is a run of NUL-terminated attribute
    fields — `worktree <path>\\0HEAD <sha>\\0branch <ref>\\0` (a bare or
    detached worktree substitutes `bare\\0` / `detached\\0` for the HEAD/branch
    fields) — and records are separated by an EMPTY field (the record's trailing
    `\\0` immediately followed by the next record's, i.e. a `\\0\\0`), with a
    final empty field at EOF. We split on NUL and take every field beginning
    `worktree ` — every record starts with exactly one such field. Each path is
    decoded with os.fsdecode (matching how `str(Path)` renders paths), so an
    undecodable path cannot raise here.
    """
    paths: list[Path] = []
    for field in stream.split(b"\0"):
        if field.startswith(b"worktree "):
            raw = field[len(b"worktree "):]
            paths.append(Path(os.fsdecode(raw)))
    return paths


def _list_worktrees(repo_root: Path) -> "list[Path] | None":
    """Return every worktree path of repo_root's repo, or None on uncertainty.

    A big feature builds in a LINKED worktree while the plan file lives in the
    MAIN checkout (planning keeps docs/plans/ in the main repo root, never a
    worktree). A linked worktree has its OWN working tree but SHARES `.git`, so
    `git status` in the main checkout cannot see uncommitted work left in the
    worktree. The guard must therefore inspect ALL worktrees, not just the
    plan's checkout, or a big feature's uncommitted worktree work would leak
    past a `status: complete` flip — the worst case, since that is exactly where
    uncommitted work is most likely (QA HIGH).

    Uses `git worktree list --porcelain -z` (NUL-delimited — see
    `_parse_worktree_list_z` for why `-z` and not the newline form). Run with the
    SAME `_scrub_git_env()` scrub the status subprocess uses, so an ambient
    GIT_DIR / GIT_WORK_TREE / GIT_COMMON_DIR cannot redirect enumeration to a
    different repo. Reads stdout as raw bytes (no text=True). Returns None
    (uncertainty -> caller allows) on git absent / timeout / non-zero exit.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain", "-z"],
            capture_output=True, timeout=5, check=False, env=_scrub_git_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    return _parse_worktree_list_z(result.stdout)


def _same_path(a: Path, b: Path) -> "bool | None":
    """Tri-state path identity: True / False / None(=indeterminate).

    - True  : a and b are raw-equal, OR both resolve successfully and are equal
      (so /tmp vs the /private/tmp symlink, or any other symlink, still matches).
    - False : both resolve successfully and are genuinely DIFFERENT locations.
    - None  : raw paths differ AND `.resolve()` raised — identity cannot be
      decided.

    The callers (`_collect_new_dirt_across_worktrees` and `_write_baseline`)
    bias an INDETERMINATE result toward treating the worktree as the plan's
    OWNER (exclude the plan file there), never as OTHER. For THIS guard the fail-open direction on uncertainty
    is to EXCLUDE the plan, not to withhold the exclusion: withholding it would
    let the plan file's own mid-edit dirt (always present at completion) be
    reported as work, manufacturing a NO-ESCAPE false BLOCK on a clean
    completion whenever resolution hiccups — which contradicts the guard's
    fail-open / no-trap contract. Returning False here (the old behavior) caused
    exactly that trap (Codex P2).
    """
    if a == b:
        return True
    try:
        return a.resolve() == b.resolve()
    except (OSError, RuntimeError):
        return None


_BASELINE_VERSION = 3  # v3: per-worktree {reg, paths} — renames never grandfathered

# Sentinel: the plan's frontmatter status could not be trusted (duplicate or
# malformed key -> AmbiguousActivePlanError). Distinct from None (cleanly
# absent) so the ARMING decision can refuse to (re)snapshot on an ambiguous
# plan instead of mistaking it for a fresh arming — see Finding 2 /
# _plan_status_strict.
_AMBIGUOUS = object()


def _plan_status_strict(text: str) -> "str | object | None":
    """Tri-state plan status for the ARMING decision (Finding 2).

    Returns the cleanly-parsed `status` string; None for a cleanly-absent
    status (no frontmatter / no status key); or the `_AMBIGUOUS` sentinel when
    the frontmatter cannot be trusted (duplicate/malformed key ->
    AmbiguousActivePlanError). The completion path keeps using `_plan_status`
    (ambiguous -> None -> not a transition -> ALLOW). Arming must NOT collapse
    ambiguous into 'absent': a mid-run malformed-frontmatter edit flipped to
    in-progress would otherwise read as a fresh arming and RE-SNAPSHOT the run's
    OWN dirt as the baseline (a leak). Passes the FULL text (same reason as
    `_plan_status`).
    """
    try:
        fm = _parse_frontmatter(text)
    except AmbiguousActivePlanError:
        return _AMBIGUOUS
    return fm.get("status")


def _baseline_file_path(plan_root: Path, plan_rel: str) -> Path:
    """Return the sidecar path for this plan's baseline snapshot.

    There is NO env override (Finding 3): an override that could point at a
    crafted permissive / missing / corrupt baseline would be a real production
    BYPASS while the block message truthfully promises 'no override env var'.
    The filename is keyed by sha256(plan_root + NUL + plan_rel)[:16] under
    tempfile.gettempdir() — the same idiom as the active-plan cache — so the
    sidecar can NEVER become tracked/committed and can never itself trip this
    gate. Tests isolate by redirecting the tempdir (TMPDIR) for the hook
    subprocess plus the natural uniqueness of each test's plan_root; they never
    inject a baseline PATH.
    """
    key = (str(plan_root) + "\0" + plan_rel).encode("utf-8", errors="surrogatepass")
    digest = hashlib.sha256(key).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"coding-team-clean-tree-baseline-{digest}.json"


def _read_sidecar_secure(path: Path) -> "str | None":
    """Read the sidecar with a NO-FOLLOW, ownership-checked open (Codex FIX 3).

    Opens `O_RDONLY | O_NOFOLLOW` so a SYMLINK planted at the sidecar path is NOT
    followed (open fails with ELOOP -> None -> fail-open), closing a symlink-swap
    that could feed a crafted permissive baseline. The ownership check runs on
    `os.fstat(fd)` of the SAME descriptor we then read — closing the
    stat-vs-read TOCTOU (an attacker cannot swap the file between a path-stat and
    a path-open). A sidecar not owned by the current euid is never trusted
    (-> None -> fail-open ALLOW). Returns the decoded text, or None on any
    open/stat/read/decode failure or a foreign owner.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        if os.fstat(fd).st_uid != os.geteuid():
            return None  # foreign-owned sidecar -> untrusted (Codex P2.3)
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            chunks.append(block)
    except OSError:
        return None
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        return b"".join(chunks).decode("utf-8")
    except ValueError:
        return None


def _write_sidecar_secure(path: Path, text: str) -> bool:
    """Write the sidecar with a NO-FOLLOW create/truncate open (Codex FIX 3).

    Opens `O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW` (mode 0600) so a SYMLINK at
    the sidecar path is NOT followed and its target is never clobbered (open
    fails with ELOOP -> returns False). Returns True on a successful write, False
    on any failure (the caller then invalidates rather than trusting a partial
    write). Overwriting an EXISTING regular file needs only file-write perm, not
    dir-write perm, so this still succeeds in a read-only directory (the basis of
    the failed-re-arm invalidation guarantee).
    """
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    except OSError:
        return False
    try:
        os.write(fd, text.encode("utf-8", errors="surrogatepass"))
        return True
    except OSError:
        return False
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _worktree_registration_id(worktree: Path) -> "int | None":
    """Per-REGISTRATION identity for a worktree — the inode of its admin gitdir
    (Codex P2.2). None on any git/stat uncertainty.

    A worktree removed and re-created at the SAME path reuses the path AND, when
    the old admin dir was pruned, even the admin-dir NAME (so `--absolute-git-dir`
    returns the same string). But the admin directory is DELETED and RECREATED,
    so its inode changes. Keying the baseline on (path, inode) means the re-added
    worktree does NOT inherit the old registration's allow-set: its lookup misses
    -> empty baseline -> all its dirt is new -> BLOCK (fail-safe, never a leak).
    The main worktree's gitdir is the repo `.git`, whose inode is stable across a
    run. Uses `--absolute-git-dir` under `_scrub_git_env()` (an ambient GIT_DIR
    would otherwise answer for the wrong repo) with a 5s timeout.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree), "rev-parse", "--absolute-git-dir"],
            capture_output=True, timeout=5, check=False, env=_scrub_git_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    gitdir = result.stdout.decode("utf-8", errors="surrogateescape").strip()
    if not gitdir:
        return None
    try:
        return os.stat(gitdir).st_ino
    except OSError:
        return None


def _worktree_resolved_path(worktree: Path) -> str:
    """Resolved absolute path of a worktree — the baseline MAP key (Codex FIX 2).

    So a /tmp vs /private/tmp symlink matches between arming and completion,
    falling back to the raw string if resolve raises. The registration identity
    (`_worktree_registration_id`) is stored as a FIELD of the entry, NOT folded
    into the key: keying by `"<path>\\0<reg>"` (the round-2 approach) serialized a
    failed lookup as the literal string `"<path>\\0None"` and then TRUSTED it —
    two bugs (a recreated worktree whose identity fails at BOTH moments inherits
    the old allow-set; an identity failure at ONLY arming permanently false-blocks
    pre-existing dirt). Keying by path and comparing the `reg` field explicitly
    lets a None `reg` (identity unknown) resolve to fail-open, while a KNOWN-but-
    CHANGED reg (a genuine re-registration) resolves to block — see
    `_collect_new_dirt_across_worktrees`.
    """
    try:
        return str(worktree.resolve())
    except (OSError, RuntimeError):
        return str(worktree)


def _dirty_entries_excluding_plan(
    worktree_root: Path, plan_rel: "str | None"
) -> "list[tuple[str, str, str]] | None":
    """Return dirty (xy, path, src) tuples other than the plan file, or None on
    ANY git uncertainty (git absent, timeout, non-zero exit) — the caller treats
    None as ALLOW. `src` is the rename/copy source path, or "" for non-renames.

    `plan_rel` is the repo-relative path to EXCLUDE, or None to exclude nothing
    (None is passed for every worktree OTHER than the one that physically owns
    the edited plan — a `docs/plans/<same-name>.md` dirty in a DIFFERENT worktree
    is a DIFFERENT physical file and is real uncommitted work, so it must not be
    excluded there; a path string never equals None, so the `path == plan_rel`
    test excludes nothing when plan_rel is None).

    Uses `-z --untracked-files=all` (NUL-delimited, never quotes/escapes; lists
    an untracked plan individually) and `_scrub_git_env()` (an ambient
    GIT_DIR/GIT_WORK_TREE/GIT_COMMON_DIR would otherwise override `-C <root>`).
    Reads stdout as raw bytes (no text=True) so a locale-undecodable filename
    cannot raise. A rename/copy entry is ALWAYS real dirt and is NEVER excluded,
    even a rename whose DEST is the plan (the SOURCE moved = real work).
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree_root), "status", "--porcelain", "-z",
             "--untracked-files=all"],
            capture_output=True, timeout=5, check=False, env=_scrub_git_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    entries: list[tuple[str, str, str]] = []
    for xy, path, src in _parse_porcelain_z(result.stdout):
        if not _is_rename_or_copy(xy) and path == plan_rel:
            continue  # the plan file's own bookkeeping — excluded
        entries.append((xy, path, src))
    return entries


def _filter_new(
    entries: "list[tuple[str, str, str]]", baseline_paths: "set[str]"
) -> "list[tuple[str, str, str]]":
    """Return the entries that count as NEW dirt.

    Non-rename entry: NEW iff its PATH is not in `baseline_paths`. Path-only by
    design (Decision 1): a tracked telemetry file that legitimately mutates
    DURING a run keeps the same path, so keying on path (not content) stops the
    gate re-blocking on it. The residual re-edit leak (a baseline path the run
    re-modifies and leaves uncommitted) is an accepted documented leak.

    Rename/copy entry: ALWAYS NEW — never grandfathered, regardless of any
    baseline record (Codex round-3). A rename's porcelain identity
    (status, dest, source) is CONTENT-BLIND: a rename staged before arming and
    then MODIFIED + re-staged during the run keeps the identical `R  dest\\0src`
    tuple, so any identity-match subtraction would LEAK the run's real work.
    "Never subtract a rename" cannot leak (any rename dirt at completion ->
    BLOCK, the safe direction); the only cost is that a pre-existing UNCHANGED
    rename also blocks — a documented, accepted limitation (commit or discard it).
    `_is_rename_or_copy` (both-column) is still used for CORRECT porcelain
    parsing (consume the 2-path record); only the subtraction of renames is gone.
    """
    new: list[tuple[str, str, str]] = []
    for (xy, path, src) in entries:
        if _is_rename_or_copy(xy) or path not in baseline_paths:
            new.append((xy, path, src))
    return new


def _read_baseline(
    plan_root: Path, plan_rel: str
) -> "dict[str, dict] | None":
    """Return {resolved_worktree_path: {"reg": int|None, "paths": set[str]}} from
    the sidecar, or None if the baseline is missing, corrupt, wrong-version, or
    for a different plan. Rename/copy dirt is never recorded (renames are never
    grandfathered — Codex round-3), so the schema carries only `reg` + `paths`.

    None means 'no usable baseline'. Per Decision 2 (fail-open) the caller
    treats None as ALLOW, NOT strict-block: strict-blocking a no-baseline plan
    would re-trap every transitional/pre-fix plan — the exact problem this change
    removes. Handled INSIDE the reader (mapped to None) so a corrupt file never
    bubbles to the top-level fail-open crash handler with the gate half-run.
    json.JSONDecodeError is a ValueError subclass, so the one `except` covers
    both a missing file (OSError) and unparseable JSON (ValueError).

    Finding 5 — a STRUCTURALLY-invalid baseline (wrong shape, wrong version,
    wrong plan_root/plan_rel, or a non-string path element) is REJECTED whole by
    returning None (-> fail-open ALLOW per Decision 2). It is NEVER salvaged into
    a partial set: silently dropping a non-string element could yield a smaller
    'valid' baseline that then FALSELY BLOCKS the run's grandfathered dirt.
    Finding 3 — the stored `plan_rel` must match the plan being completed (not
    just plan_root), so a sidecar produced for a DIFFERENT plan (hash collision,
    or a stale/renamed sidecar at the same key) is rejected rather than trusted.

    Codex P2.1 — the version must be an ACTUAL int, not merely `== 1`: JSON
    `true` (Python `True == 1`) and `1.0` would otherwise pass and be consumed as
    a valid-but-empty baseline, then FALSELY BLOCK pre-existing dirt. `type(v) is
    int` rejects bool (a subclass of int) and float.
    Codex P2.3 / FIX 3 — the read goes through `_read_sidecar_secure`: a
    NO-FOLLOW open (a symlink at the sidecar path is rejected, closing a symlink
    swap) with an ownership check on the SAME descriptor (fstat, no TOCTOU). A
    sidecar not owned by the current euid — a stale/foreign file that a failed
    re-arm could not overwrite — is never trusted (-> None -> fail-open ALLOW).
    """
    path = _baseline_file_path(plan_root, plan_rel)
    raw = _read_sidecar_secure(path)  # O_NOFOLLOW + fstat ownership (Codex FIX 3)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    if type(version) is not int or version != _BASELINE_VERSION:
        return None  # Codex P2.1 — reject bool/float; require an actual int
    if data.get("plan_root") != str(plan_root):
        return None  # sidecar written for a different repo (hash-collision guard)
    if data.get("plan_rel") != plan_rel:
        return None  # sidecar written for a DIFFERENT plan at the same key
    worktrees = data.get("worktrees")
    if not isinstance(worktrees, dict):
        return None
    out: dict[str, dict] = {}
    for key, entry in worktrees.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            return None
        reg = entry.get("reg")
        if reg is not None and type(reg) is not int:  # reg is a real int or null
            return None
        paths = entry.get("paths")
        if not isinstance(paths, list):
            return None
        path_set: set[str] = set()
        for element in paths:
            if not isinstance(element, str):
                return None  # structurally invalid -> reject the WHOLE baseline
            path_set.add(element)
        out[key] = {"reg": reg, "paths": path_set}
    return out


def _invalidate_sidecar(path: Path) -> None:
    """Best-effort render the sidecar ABSENT or UNUSABLE (Codex P2.3).

    Prefer unlink (which removes a symlink itself, never its target). If unlink
    raises a non-FileNotFound OSError — e.g. the sidecar lives in a directory we
    cannot write (no dir-write perm) — fall back to OVERWRITING its content with
    bytes that `_read_baseline` rejects (invalid JSON), via `_write_sidecar_secure`
    (O_NOFOLLOW, so a symlink is NOT followed to clobber its target — Codex
    FIX 3). Overwriting an EXISTING regular file needs only file-write perm, NOT
    dir-write perm, so it succeeds even when unlink cannot. The point: a failed
    re-arm must never leave a VALID stale baseline that completion would trust and
    use to grandfather this run's new work. If even the overwrite fails (a
    foreign-uid file, or a symlink), the read side's no-follow + ownership check
    (`_read_sidecar_secure`) still refuses to trust it. Best-effort teardown;
    the read side is the backstop.
    """
    try:
        path.unlink()
        return
    except FileNotFoundError:
        return
    except OSError:
        pass
    _write_sidecar_secure(path, "__INVALIDATED__")  # -> JSON parse fails -> None


def _write_baseline(plan_root: Path, plan_rel: str, worktree_root: Path) -> None:
    """Snapshot the current per-worktree dirty PATH set (excluding the plan
    file) and persist it to the sidecar. Best-effort, ALL-or-nothing: on ANY
    uncertainty (cannot enumerate worktrees, a worktree that EXISTS now is
    unreadable, or the write fails) it leaves NO usable baseline behind —
    completion then fails OPEN (ALLOW), never blocking on a half-captured
    snapshot and never consuming a STALE one.

    Finding 1 / Codex P2.3 — INVALIDATE FIRST, and GUARANTEE it. A genuine
    (re-)arming SUPERSEDES any prior baseline, so the existing sidecar is
    invalidated BEFORE capture via `_invalidate_sidecar` (unlink, or if the dir
    is unwritable, overwrite its content to unparseable). If capture then fails,
    no USABLE baseline remains -> completion fail-opens (Decision 2), instead of
    silently reusing the previous run's snapshot (a stale baseline -> a targeted
    leak that grandfathers new work). The earlier version swallowed a non-
    FileNotFound unlink OSError and, on a subsequent bail, left a VALID stale
    sidecar (Codex P2.3); invalidating by content-overwrite closes that.

    Overwrites/removes the sidecar on every call: the caller only invokes this on
    a genuine arming (a cleanly-parsed non-in-progress PRE -> in-progress; never
    an in-progress re-edit or an ambiguous PRE — see `_is_arming_transition`), so
    a stale prior baseline must not survive and widen the allow-set (F4).
    """
    path = _baseline_file_path(plan_root, plan_rel)
    # Invalidate any prior baseline FIRST and guarantee it is not left VALID
    # (Finding 1 + Codex P2.3).
    _invalidate_sidecar(path)
    worktrees = _list_worktrees(worktree_root)
    if worktrees is None:
        # cannot enumerate -> leave no usable baseline -> completion fails open.
        _invalidate_sidecar(path)
        return
    snapshot: dict[str, dict] = {}
    for worktree in worktrees:
        exclude = None if _same_path(worktree, worktree_root) is False else plan_rel
        entries = _dirty_entries_excluding_plan(worktree, exclude)
        if entries is None:
            # an existing worktree is unreadable -> refuse a partial baseline.
            _invalidate_sidecar(path)
            return
        # Record only the non-rename dirt PATHS (path-only subtraction). Rename/
        # copy entries are deliberately NOT recorded — they are never
        # grandfathered (Codex round-3), so any rename dirt at completion blocks.
        # Store the registration id as a FIELD (may be null) keyed by resolved
        # path, so a None identity resolves to fail-open, not a trusted
        # `path\0None` key (FIX 2).
        snapshot[_worktree_resolved_path(worktree)] = {
            "reg": _worktree_registration_id(worktree),
            "paths": [entry_path for (xy, entry_path, _src) in entries
                      if not _is_rename_or_copy(xy)],
        }
    baseline = {
        "version": _BASELINE_VERSION,
        "plan_root": str(plan_root),
        "plan_rel": plan_rel,
        "armed_ts": time.time(),
        "worktrees": snapshot,
    }
    if not _write_sidecar_secure(path, json.dumps(baseline)):
        # Write failed (or the path is a symlink) -> ensure no partial/stale
        # content is left readable.
        _invalidate_sidecar(path)


def _is_arming_transition(tool_name: str, tool_input: dict, target: Path) -> bool:
    """True iff this edit arms the baseline: a POST status of `in-progress` from
    a PRE status that is a CLEANLY-PARSED non-in-progress value — `planned`,
    `complete`, any other clean status, or a cleanly-absent status.

    The baseline-capture trigger (Finding 2). Cases:
    - PRE already `in-progress` (a mid-run checkbox tick) -> NOT arming -> no
      re-snapshot, so mid-run edits never clobber the baseline.
    - PRE `complete` (or any clean non-in-progress) -> IS a fresh (re-)arming, so
      a `complete -> in-progress` reopen re-snapshots from scratch rather than
      leaving a missing/stale baseline. `_write_baseline` invalidates-first, so
      the reopen replaces the old snapshot.
    - PRE genuinely ABSENT (FileNotFoundError — a brand-new plan Written straight
      to `in-progress`) -> IS arming, so plans that skip `planned` still arm.
    - PRE AMBIGUOUS (duplicate/malformed frontmatter -> `_AMBIGUOUS`) -> NOT
      arming: leave any existing baseline untouched. Collapsing ambiguous into
      'absent' would let a mid-run malformed-frontmatter edit re-snapshot the
      run's OWN dirt as the baseline (a leak). If no baseline exists, completion
      fail-opens — never worse than the pre-fix state.
    - PRE EXISTING-but-unreadable (PermissionError/other OSError) -> NOT arming,
      so a transient read error cannot clobber a good baseline.
    Never raises.
    """
    try:
        pre = target.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        pre = ""  # genuinely absent -> cleanly-none PRE -> armable
    except (OSError, PermissionError):
        return False  # existing-but-unreadable -> uncertain -> do NOT (re)arm
    pre_status = _plan_status_strict(pre) if pre else None
    if pre_status is _AMBIGUOUS:
        return False  # malformed/duplicate PRE -> do NOT re-snapshot (leak guard)
    if pre_status == "in-progress":
        return False  # already armed; a mid-run edit is not a fresh arming
    # pre_status is now a cleanly-parsed non-in-progress value (planned, complete,
    # some other status, or None cleanly-absent) — all armable.
    post = _post_edit_content(tool_name, tool_input, pre)
    if post is None:
        return False
    return _plan_status_strict(post) == "in-progress"


def _collect_new_dirt_across_worktrees(
    plan_worktree_root: Path, plan_rel: str, baseline: "dict[str, dict]"
) -> "dict[Path, list[str]] | None":
    """First worktree with confirmed NEW (non-baseline) dirt -> {that worktree:
    formatted `XY path` strings}. None if worktree enumeration is uncertain (git
    error) -> caller ALLOWs; {} if every worktree is clean-or-baseline-only ->
    caller ALLOWs.

    Mirrors the previous collector's short-circuit (return on the first confirmed
    dirty worktree — each `git status` has its own 5s timeout and the dispatcher
    kills the handler at 30s, so scanning all first risks discarding early dirt)
    and its per-worktree plan-exclusion via `_same_path` tri-state (only a
    DEFINITIVE non-owner `False` withholds the plan exclusion; True and the
    indeterminate None both EXCLUDE, so a resolve hiccup never manufactures a
    false block). New in this change: subtract each worktree's baseline path set
    before deciding. A worktree ABSENT from the baseline (created after arming)
    has an empty base set -> ALL its dirt is new -> blocks (the safe direction).
    Per-worktree git uncertainty (`_dirty_entries_excluding_plan` -> None) is
    SKIPPED, not a global allow: positive dirt elsewhere still blocks.

    Registration-identity handling (Codex FIX 2) — the baseline is keyed by
    resolved worktree PATH, with the registration id (`reg`) as a FIELD. For each
    worktree:
    - identity unknown NOW (cur_reg None) -> baseline UNAVAILABLE -> fail-open
      (skip this worktree), never a permanent false-block from a git hiccup;
    - not in the baseline at all -> created after arming -> empty base -> BLOCK
      its dirt (the safe direction: linked feature-build / concurrent worktrees);
    - stored `reg` is None (identity was unknown at ARMING) -> UNAVAILABLE ->
      fail-open (skip), never inherit a `path\0None` allow-set, never false-block;
    - stored `reg` KNOWN but != cur_reg -> a genuine RE-REGISTRATION at the same
      path -> empty base -> BLOCK (must not inherit the old allow-set, P2.2);
    - stored `reg` == cur_reg -> the SAME registration -> subtract its baseline.
    """
    worktrees = _list_worktrees(plan_worktree_root)
    if worktrees is None:
        return None
    for worktree in worktrees:
        exclude = None if _same_path(worktree, plan_worktree_root) is False else plan_rel
        entries = _dirty_entries_excluding_plan(worktree, exclude)
        if entries is None:
            continue
        cur_reg = _worktree_registration_id(worktree)
        if cur_reg is None:
            continue  # identity unknown now -> baseline unavailable -> fail-open (skip)
        base = baseline.get(_worktree_resolved_path(worktree))
        if base is None:
            base_paths: set[str] = set()  # created after arming -> block dirt
        elif base["reg"] is None:
            continue  # identity unknown at arming -> unavailable -> fail-open (skip)
        elif base["reg"] != cur_reg:
            base_paths = set()  # re-registered at same path -> block
        else:
            base_paths = base["paths"]
        new = _filter_new(entries, base_paths)
        if new:
            return {worktree: [f"{xy} {path}" for (xy, path, _src) in new]}
    return {}


def main() -> None:
    event = _event.parse_event()
    if not event:
        return
    if _event.get_tool_name(event) not in ("Edit", "Write"):
        return
    tool_input = _event.get_tool_input(event)
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    worktree_root, plan_root = _resolve_target_git_roots(file_path)
    if worktree_root is None or plan_root is None:
        return  # not in any git repo -> not gated
    if not _is_plan_file(file_path, worktree_root):
        return  # not a docs/plans/*.md file -> allow

    target = Path(file_path)

    # Arming: snapshot the pre-run dirt on a clean non-in-progress -> in-progress
    # transition (planned/complete/absent PRE; ambiguous PRE never arms).
    if _is_arming_transition(_event.get_tool_name(event), tool_input, target):
        try:
            plan_rel = str(target.resolve().relative_to(worktree_root.resolve()))
        except (OSError, ValueError, RuntimeError):
            return  # cannot locate plan -> skip snapshot -> completion fails open
        _write_baseline(plan_root, plan_rel, worktree_root)
        return  # arming is never cleanliness-gated

    if not _is_completion_transition(_event.get_tool_name(event), tool_input, target):
        return  # not the in-progress -> complete transition -> allow

    try:
        plan_rel = str(target.resolve().relative_to(worktree_root.resolve()))
    except (OSError, ValueError, RuntimeError):
        return  # cannot locate plan within its repo -> uncertainty -> allow

    baseline = _read_baseline(plan_root, plan_rel)
    if baseline is None:
        return  # no usable baseline (missing/corrupt) -> fail-open ALLOW (Decision 2)

    dirty_by_worktree = _collect_new_dirt_across_worktrees(
        worktree_root, plan_rel, baseline
    )
    if dirty_by_worktree is None:
        return  # git uncertainty (worktree enumeration failed) -> allow
    if not dirty_by_worktree:
        return  # no NEW dirt anywhere (only pre-existing / plan file) -> allow

    sections = []
    for worktree, lines in dirty_by_worktree.items():
        listing = "\n".join(f"    {line}" for line in lines)
        sections.append(f"  Worktree: {worktree}\n{listing}")
    body = "\n\n".join(sections)
    _output.block(
        "BLOCKED: cannot mark this plan `status: complete` — a working tree "
        "has uncommitted work created since this plan started.\n\n"
        f"Plan: {target}\n"
        f"Repo: {worktree_root}\n\n"
        "New (since the plan armed) uncommitted / untracked across ALL worktrees "
        "of the repo (excluding the plan file and any dirt that already existed "
        "when the plan started):\n"
        f"{body}\n\n"
        "No coding-team run is complete until its work is committed. A big "
        "feature may have built in a LINKED worktree — check the worktree(s) "
        "named above, not just your current checkout. Before flipping the plan "
        "to `status: complete`:\n"
        "  - Commit the files above (git add <files> && git commit), OR\n"
        "  - If any are genuine garbage, discard them (git checkout -- <file>, "
        "git clean -f <file>).\n"
        "Then retry marking the plan complete. There is NO override env var — a "
        "clean tree (of NEW work) is the only way through.\n\n"
        "Known rationalization: 'the implementer said it committed' — verify, "
        "don't trust; the tree above is the ground truth."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — fail OPEN: an unrelated edit must never be trapped
        print(f"clean-tree-gate.py: crashed with {exc!r} — failing open, continuing", file=sys.stderr)
    sys.exit(0)
