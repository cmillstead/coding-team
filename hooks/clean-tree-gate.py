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
import os
import subprocess
import sys

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


def _parse_porcelain_z(stream: bytes) -> "list[tuple[str, str]]":
    """Parse `git status --porcelain -z` BYTES into (xy, path) entries.

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
    starting `R`/`C`) is TWO NUL fields: `XY <dest>\\0<src>\\0` — the dest first
    (the `-z` ordering is dest-then-source), then the source, which we consume
    but do not return. Returns (xy, path) with `path` the primary/dest path.
    """
    fields = stream.split(b"\0")
    entries: list[tuple[str, str]] = []
    i = 0
    while i < len(fields):
        field = fields[i]
        if not field:
            i += 1
            continue
        xy = field[:2].decode("ascii", errors="replace")
        path = field[3:].decode("utf-8", errors="surrogateescape")  # skip XY + space
        entries.append((xy, path))
        # A rename/copy record carries a second NUL field (the source path).
        if xy and xy[0] in ("R", "C"):
            i += 2
        else:
            i += 1
    return entries


def _dirty_excluding_plan(worktree_root: Path, plan_rel: str) -> "list[str] | None":
    """Return dirty entries (as `XY path` strings) other than the plan file.

    Returns None on ANY git uncertainty (git absent, timeout, non-zero exit) —
    the caller treats None as ALLOW.

    Uses `-z` (NUL-delimited, never quotes/escapes paths — so a plan path like
    `docs/plans/my plan.md` still equals plan_rel and is excluded; porcelain v1
    would print it quoted and the exclusion would miss, wrongly BLOCKing a clean
    completion) and `--untracked-files=all` (lists an untracked plan file
    individually instead of collapsing its dir to `?? docs/`, so the plan can be
    excluded even when its directory is otherwise untracked).

    FIX 8: the subprocess env is scrubbed of GIT_*-affecting vars via the SAME
    `_scrub_git_env()` the target-root discovery already uses — an ambient
    GIT_DIR / GIT_WORK_TREE / GIT_COMMON_DIR would otherwise override `-C <root>`
    and make git inspect a DIFFERENT (possibly clean) repo, leaking a dirty
    completion. FIX 9: `capture_output=True` withOUT `text=True`, so stdout is
    raw bytes and no locale decode can raise here.

    A rename/copy entry is ALWAYS real dirt and is NEVER excluded — even a
    rename whose DEST is the plan means the SOURCE moved, which is real
    uncommitted work. Only a NON-rename/copy entry whose single path == plan_rel
    is the plan file's own mid-edit bookkeeping and is excluded.
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
    dirty = []
    for xy, path in _parse_porcelain_z(result.stdout):
        is_rename_or_copy = bool(xy) and xy[0] in ("R", "C")
        if not is_rename_or_copy and path == plan_rel:
            continue  # the plan file's own bookkeeping — excluded
        dirty.append(f"{xy} {path}")
    return dirty


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

    `git worktree list --porcelain` emits one `worktree <path>` line per
    worktree (main first, then each linked worktree). Run with the SAME
    `_scrub_git_env()` scrub the status subprocess uses, so an ambient
    GIT_DIR / GIT_WORK_TREE / GIT_COMMON_DIR cannot redirect enumeration to a
    different repo. Reads stdout as raw bytes (no text=True) and decodes each
    path with os.fsdecode — matching how `str(Path)` renders paths — so an
    undecodable path cannot raise here. Returns None (uncertainty -> caller
    allows) on git absent / timeout / non-zero exit.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            capture_output=True, timeout=5, check=False, env=_scrub_git_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    paths: list[Path] = []
    for line in result.stdout.split(b"\n"):
        if line.startswith(b"worktree "):
            raw = line[len(b"worktree "):]
            paths.append(Path(os.fsdecode(raw)))
    return paths


def _collect_dirt_across_worktrees(
    plan_repo_root: Path, plan_rel: str
) -> "dict[Path, list[str]] | None":
    """Map each dirty worktree to its non-excluded dirt, across ALL worktrees.

    Returns None if the worktree enumeration itself is uncertain (git error) —
    the caller treats None as ALLOW. Otherwise returns a dict of
    {worktree_path: [dirty entries]} for every worktree that has confirmed
    non-excluded dirt (an empty dict means every worktree is clean -> allow).

    Per-worktree uncertainty (a `_dirty_excluding_plan` returning None) is
    SKIPPED, not treated as a global allow: confirmed dirt found in one worktree
    still BLOCKs even if another worktree's status could not be determined —
    positive evidence of uncommitted work wins over uncertainty elsewhere, while
    a run that finds no confirmed dirt anywhere still allows. The plan file's
    repo-relative path is excluded in EVERY worktree (harmless where the plan
    file is not present or not dirty).
    """
    worktrees = _list_worktrees(plan_repo_root)
    if worktrees is None:
        return None
    dirty_by_worktree: dict[Path, list[str]] = {}
    for worktree in worktrees:
        dirty = _dirty_excluding_plan(worktree, plan_rel)
        if dirty:
            dirty_by_worktree[worktree] = dirty
    return dirty_by_worktree


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

    worktree_root, _plan_root = _resolve_target_git_roots(file_path)
    if worktree_root is None:
        return  # not in any git repo -> not gated
    if not _is_plan_file(file_path, worktree_root):
        return  # not a docs/plans/*.md file -> allow

    target = Path(file_path)
    if not _is_completion_transition(_event.get_tool_name(event), tool_input, target):
        return  # not the in-progress -> complete transition -> allow

    try:
        plan_rel = str(target.resolve().relative_to(worktree_root.resolve()))
    except (OSError, ValueError, RuntimeError):
        return  # cannot locate plan within its repo -> uncertainty -> allow

    dirty_by_worktree = _collect_dirt_across_worktrees(worktree_root, plan_rel)
    if dirty_by_worktree is None:
        return  # git uncertainty (worktree enumeration failed) -> allow
    if not dirty_by_worktree:
        return  # every worktree clean (excluding the plan file) -> allow

    sections = []
    for worktree, lines in dirty_by_worktree.items():
        listing = "\n".join(f"    {line}" for line in lines)
        sections.append(f"  Worktree: {worktree}\n{listing}")
    body = "\n\n".join(sections)
    _output.block(
        "BLOCKED: cannot mark this plan `status: complete` — a working tree "
        "still has uncommitted work.\n\n"
        f"Plan: {target}\n"
        f"Repo: {worktree_root}\n\n"
        "Uncommitted / untracked across ALL worktrees of the repo (excluding "
        "the plan file):\n"
        f"{body}\n\n"
        "No coding-team run is complete until its work is committed. A big "
        "feature may have built in a LINKED worktree — check the worktree(s) "
        "named above, not just your current checkout. Before flipping the plan "
        "to `status: complete`:\n"
        "  - Commit the files above (git add <files> && git commit), OR\n"
        "  - If any are genuine garbage, discard them (git checkout -- <file>, "
        "git clean -f <file>).\n"
        "Then retry marking the plan complete. There is NO override env var — a "
        "clean tree is the only way through.\n\n"
        "Known rationalization: 'the implementer said it committed' — verify, "
        "don't trust; the tree above is the ground truth."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — fail OPEN: an unrelated edit must never be trapped
        print(f"clean-tree-gate.py: crashed with {exc!r} — failing open, continuing", file=sys.stderr)
    sys.exit(0)
