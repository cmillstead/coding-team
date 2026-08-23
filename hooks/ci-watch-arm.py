#!/usr/bin/env python3
"""PostToolUse/Bash handler: arm the CI watcher after a CI-triggering command.

Invoked by posttooluse-dispatcher.py in its tool_name==Bash branch. Detects a
push, a PR-create, or a PR-merge, resolves what the watcher must attach to, and
fire-and-forgets a DETACHED ci-watcher.py process. Returns in well under 100ms
and NEVER blocks the push (side-effect-only; emits no decision).

Arm is LOCAL-GIT-ONLY and side-effect-only, so it returns in well under 100ms and
never blocks the turn: every gh (network) call happens in the detached watcher.

Two attach strategies, keyed on the trigger type:

  - push / pr-create -> mode "push". Resolve the LOCAL pushed source SHA(s) +
    current branch + the pushed-remote nwo; the watcher matches the Actions run
    by head_sha (with the `updated_at >= armed_at` recency guard).

  - pr-merge -> mode "merge". The local HEAD is STALE at merge time (the merge
    commit is created on the remote base branch), so arm does NOT match on it.
    Arm parses only the PR selector + repo override locally and passes them to the
    watcher; the WATCHER resolves the merge-commit SHA (gh pr view) and matches by
    that SHA, or falls back to a safe-broad watch when the merge commit does not
    yet exist (--auto / not-yet-merged).

Structural replacement for the memory note feedback_monitor_ci_after_push.md,
which depended on Claude remembering to watch CI. See harness decision
post-push-ci-watch-2026-07-09.

Idempotency + cleanup:
  - Armed-lock ~/.claude/ci-watch/armed/<repo>-<digest>.lock prevents
    double-arming the same target. The digest keys on repo identity (nwo +
    repo_root) + the sorted SHA set + mode + selector for BOTH modes, so distinct
    repos/targets/merges never collide. The watcher removes its own lock on exit.
  - On each invocation, stale armed-locks older than STALE_LOCK_SECS (orphaned
    watchers) are swept, and arming is refused above MAX_ARMED_WATCHERS.

Escape hatch: CT_CI_WATCH_DISABLE=1 -> no-op.
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _lib.git import (git_invocations, has_git_subcommand,
                          resolve_command_target_dir, resolve_repo_root, _split_glued_separators)
except Exception:  # noqa: BLE001 - handler must never crash the dispatcher
    git_invocations = has_git_subcommand = resolve_command_target_dir = resolve_repo_root = None
    _split_glued_separators = None

HOME = Path(os.path.expanduser("~"))
CI_WATCH_DIR = HOME / ".claude" / "ci-watch"
ARMED_DIR = CI_WATCH_DIR / "armed"
WATCHER = Path(__file__).resolve().parent / "ci-watcher.py"
STALE_LOCK_SECS = 30 * 60
MAX_ARMED_WATCHERS = 8   # ceiling on concurrent detached watchers; refuse to arm above it

# Trigger modes. The watcher's 9 positional args are, in order:
#   repo_root, branch, shas_csv, lock, nwo, armed_at, broad, mode, selector
# so `mode` is the 8th and `selector` the 9th (NOT the 6th).
MODE_PUSH = "push"
MODE_MERGE = "merge"

_SHELL_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})
_GH_VALUE_OPTS = frozenset({"-R", "--repo", "-b", "--body", "-F", "--body-file",
                            "--match-head-commit", "-t", "--subject", "-A", "--author-email"})


def _gh_tokens(command):
    """Tokenize a command for the gh path, normalizing GLUED shell separators via the
    same routine the git parser uses (`gh pr merge 42&&echo` -> ...'42','&&','echo')."""
    normalized = _split_glued_separators(command) if _split_glued_separators else command
    try:
        return shlex.split(normalized)
    except ValueError:
        return normalized.split()


def _gh_segment(tokens, gh_index):
    segment = []
    for following in tokens[gh_index + 1:]:
        if following in _SHELL_SEPARATORS:
            break
        segment.append(following)
    return segment


def _gh_positionals(segment):
    positionals = []
    cursor = 0
    while cursor < len(segment):
        token = segment[cursor]
        if token in _GH_VALUE_OPTS:
            cursor += 2
            continue
        if token.startswith("-"):
            cursor += 1
            continue
        positionals.append(token)
        cursor += 1
    return positionals


def _is_gh_head(tokens, index):
    """True iff tokens[index] is a `gh` token in COMMAND-HEAD position — the start
    of a shell segment (index 0 or right after a shell separator). Mirrors the git
    parser's head detection so `echo gh pr merge 42` (gh in argument position) is
    never treated as a real gh command."""
    if tokens[index].rsplit("/", 1)[-1] != "gh":
        return False
    return index == 0 or tokens[index - 1] in _SHELL_SEPARATORS


def _classify_trigger(command):
    """Classify a CI-triggering command as push, pr-create, or pr-merge.

    Returns one of "push", "pr-create", "pr-merge", or None (not CI-triggering).
    The gh path requires `gh` to be the command HEAD of a shell segment, is
    glued-separator-aware, and skips option VALUES (so `-R o/n` before the
    subcommand doesn't shift the positional grammar); push detection reuses the
    shared git parser. A push and a pr-create both take the headSha path
    (MODE_PUSH); only a pr-merge takes the merge path (MODE_MERGE).
    """
    tokens = _gh_tokens(command)
    for index, _tok in enumerate(tokens):
        if not _is_gh_head(tokens, index):
            continue
        positionals = _gh_positionals(_gh_segment(tokens, index))
        if positionals[:2] == ["pr", "create"]:
            return "pr-create"
        if positionals[:2] == ["pr", "merge"]:
            return "pr-merge"
    if has_git_subcommand is not None and has_git_subcommand(command, "push"):
        return "push"
    return None


def _pr_selector(command):
    """The PR selector argument of a `gh pr merge <selector>` command (a number,
    URL, or branch), or None when the merge targets the current branch's PR. Uses
    the glued-separator-aware tokenizer, requires `gh` command-head position, and
    skips gh option VALUES."""
    tokens = _gh_tokens(command)
    for index, _tok in enumerate(tokens):
        if not _is_gh_head(tokens, index):
            continue
        positionals = _gh_positionals(_gh_segment(tokens, index))
        if positionals[:2] == ["pr", "merge"]:
            return positionals[2] if len(positionals) > 2 else None
    return None


def _gh_repo_override(command):
    """The `-R`/`--repo` owner/name override on a gh command (command-head), or None."""
    tokens = _gh_tokens(command)
    for index, _tok in enumerate(tokens):
        if not _is_gh_head(tokens, index):
            continue
        segment = _gh_segment(tokens, index)
        cursor = 0
        while cursor < len(segment):
            token = segment[cursor]
            if token in ("-R", "--repo"):
                return segment[cursor + 1] if cursor + 1 < len(segment) else None
            if token.startswith("--repo="):
                return token.split("=", 1)[1]
            cursor += 1
    return None


_PUSH_VALUE_OPTS = frozenset({"-o", "--push-option", "--receive-pack", "--exec", "--recurse-submodules"})
_AMBIGUOUS_PUSH_FLAGS = frozenset({"--branches", "--mirror"})   # --mirror is precise-able but treat broad-safe
_DELETE_PUSH_FLAGS = frozenset({"--delete", "-d"})
_DRY_RUN_PUSH_FLAGS = frozenset({"--dry-run", "-n"})
MAX_LOCAL_REFS = 3   # arm resolves at most this many refs locally; more -> safe-broad


def _is_dry_run_push(command):
    """True when the push is a `--dry-run`/`-n` push: nothing is actually sent, so
    arm must NOT spawn a watcher (it would occupy a slot and could false-attribute an
    already-running same-SHA failure)."""
    if git_invocations is None:
        return False
    try:
        for subcommand, args in git_invocations(command):
            if subcommand == "push" and any(a in _DRY_RUN_PUSH_FLAGS for a in args):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _url_to_nwo(url):
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url or "")
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _sha_set(repo_root, refs):
    out = set()
    for ref in refs:
        sha = _git_out(repo_root, ["rev-parse", ref])
        if sha:
            out.add(sha)
    return out


def _local_refs(repo_root, prefix):
    listing = _git_out(repo_root, ["for-each-ref", prefix, "--format=%(objectname)"])
    return [line for line in listing.split() if line] if listing else []


def _push_args(command):
    """(remote, refspecs, all_flag, tags_flag, mirror_flag) for the push invocation,
    or None if there is no push subcommand. --repo overrides the positional remote."""
    if git_invocations is None:
        return None
    try:
        invocations = git_invocations(command)
    except Exception:  # noqa: BLE001
        return None
    for subcommand, args in invocations:
        if subcommand != "push":
            continue
        remote = None
        repo_opt = all_flag = tags_flag = mirror_flag = False
        positionals = []
        cursor = 0
        while cursor < len(args):
            token = args[cursor]
            if token == "--all":
                all_flag = True
                cursor += 1
                continue
            if token == "--tags":
                tags_flag = True
                cursor += 1
                continue
            if token == "--mirror":
                mirror_flag = True
                cursor += 1
                continue
            if token == "--repo":
                repo_opt = True
                remote = args[cursor + 1] if cursor + 1 < len(args) else None
                cursor += 2
                continue
            if token.startswith("--repo="):
                repo_opt = True
                remote = token.split("=", 1)[1]
                cursor += 1
                continue
            if token in _PUSH_VALUE_OPTS:
                cursor += 2
                continue
            if token.startswith("-"):
                cursor += 1
                continue
            positionals.append(token)
            cursor += 1
        refspecs = positionals if repo_opt else positionals[1:]
        if remote is None and positionals and not repo_opt:
            remote = positionals[0]
        return remote, refspecs, all_flag, tags_flag, mirror_flag
    return None


def _pushed_source_shas(repo_root, command):
    """Local commit SHAs a `git push` sends. Empty when there is no push subcommand
    (e.g. gh pr create) so the caller can fall back to HEAD."""
    parsed = _push_args(command)
    if parsed is None:
        return set()
    _remote, refspecs, all_flag, tags_flag, mirror_flag = parsed
    refs = []
    if mirror_flag:
        refs += _local_refs(repo_root, "refs/")
    if all_flag:
        refs += _local_refs(repo_root, "refs/heads")
    if tags_flag:
        refs += _local_refs(repo_root, "refs/tags")
    for refspec in refspecs:
        src = refspec.lstrip("+").split(":")[0]
        if src:
            refs.append(src)
    if not refs:
        refs = ["HEAD"]
    return _sha_set(repo_root, refs)


def _is_ambiguous_push(command):
    """True when the push form cannot be precisely + cheaply enumerated -> safe-broad
    watch. Bulk pushes (--all/--tags/--mirror, or more than MAX_LOCAL_REFS refspecs)
    would need N synchronous rev-parse calls, which would block the completed push, so
    they take the broad path instead. Delete / source-less refspecs (`:old`, --delete)
    have no source SHA to watch, so they too take the broad path (never a wrong SHA)."""
    parsed = _push_args(command)
    if parsed is None:
        return False
    _remote, refspecs, all_flag, tags_flag, mirror_flag = parsed
    if all_flag or tags_flag or mirror_flag:
        return True                          # bulk -> broad, no per-ref rev-parse (P1)
    if len(refspecs) > MAX_LOCAL_REFS:
        return True                          # too many refs to resolve fast -> broad (P1)
    if git_invocations is None:
        return True
    try:
        for subcommand, args in git_invocations(command):
            if subcommand != "push":
                continue
            if any(a in _AMBIGUOUS_PUSH_FLAGS for a in args):
                return True
            if any(a in _DELETE_PUSH_FLAGS for a in args):
                return True                  # `git push --delete` -> broad (P2)
    except Exception:  # noqa: BLE001
        return True
    for refspec in refspecs:
        if refspec.lstrip("+").startswith(":") or "*" in refspec:
            return True                      # delete `:old` / wildcard -> broad (P2)
    return False


def _pushed_branch(repo_root, command):
    """Best-effort reported branch: the DESTINATION of the first simple refspec (so
    `git push origin main` while on feat/x reports `main`, not the checkout). `src:dst`
    -> dst; a plain `src` -> src; `refs/heads/x` -> x. Falls back to the local current
    branch (bare `git push`, gh pr create)."""
    parsed = _push_args(command)
    if parsed is not None:
        _remote, refspecs, _all, _tags, _mirror = parsed
        for refspec in refspecs:
            spec = refspec.lstrip("+")
            dst = spec.split(":")[-1] if ":" in spec else spec
            dst = dst.rsplit("/", 1)[-1]
            if dst:
                return dst
    return _git_out(repo_root, ["branch", "--show-current"]) or "-"


def _push_remote_nwo(repo_root, command):
    """owner/name of the ACTUAL pushed remote (A-2): the --repo value, else the first
    positional, else origin; a URL is parsed directly, a name resolved via git remote."""
    parsed = _push_args(command)
    remote = parsed[0] if parsed else None
    if not remote:
        return _nwo(repo_root)
    if ":" in remote or remote.endswith(".git") or remote.count("/") >= 2:
        return _url_to_nwo(remote) or _nwo(repo_root)
    url = _git_out(repo_root, ["remote", "get-url", remote])
    return (_url_to_nwo(url) if url else None) or _nwo(repo_root)


def _resolve_target(command, mode):
    """Resolve what the watcher must attach to for command under mode.

    Returns the 8-tuple (repo_root, branch, target_shas, armed_at, nwo, broad, mode,
    selector) or None. LOCAL-GIT-ONLY — no gh calls (arm must stay sub-100ms). For a
    merge, target_shas is just the local HEAD lock-anchor and `selector` carries the
    PR selector; the detached watcher resolves the actual merge-commit SHA.
    """
    if resolve_command_target_dir is None or resolve_repo_root is None:
        target_dir = os.getcwd()
        repo_root = _repo_root_fallback(target_dir)
    else:
        target_dir = resolve_command_target_dir(command)
        repo_root = resolve_repo_root(target_dir) or _repo_root_fallback(target_dir)
    if not repo_root:
        return None

    armed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    branch = _git_out(repo_root, ["branch", "--show-current"]) or "-"
    head = _sha_set(repo_root, ["HEAD"])

    if mode == MODE_MERGE:
        # LOCAL-ONLY (sub-100ms, never blocks the turn): resolving the merge-commit
        # SHA and base branch needs gh, so the WATCHER does that (detached). Arm
        # only parses the repo override + selector locally and passes them through.
        # HEAD is just the lock anchor — the watcher ignores it for matching, since
        # the local HEAD is the STALE pre-merge sha.
        nwo = _gh_repo_override(command) or _nwo(repo_root)
        selector = _pr_selector(command) or "-"
        return repo_root, branch, head, armed_at, nwo, "0", MODE_MERGE, selector

    # MODE_PUSH (git push OR gh pr create). nwo = gh -R override, else the ACTUAL
    # pushed remote. Ambiguous forms -> safe-broad.
    if _is_dry_run_push(command):
        return None  # --dry-run pushed nothing: do not arm
    nwo = _gh_repo_override(command) or _push_remote_nwo(repo_root, command)
    if _is_ambiguous_push(command):
        return repo_root, branch, head, armed_at, nwo, "1", MODE_PUSH, "-"
    shas = _pushed_source_shas(repo_root, command) or head    # gh pr create -> HEAD (R3-2)
    if not shas:
        return None
    push_branch = _pushed_branch(repo_root, command)          # report the pushed ref (F6)
    return repo_root, push_branch, shas, armed_at, nwo, "0", MODE_PUSH, "-"


def _repo_root_fallback(directory):
    return _git_out(directory, ["rev-parse", "--show-toplevel"], use_C=True)


def _git_out(where, args, use_C=True):
    """Run git in where, return stripped stdout or None."""
    cmd = ["git", "-C", where, *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None


def _nwo(repo_root):
    """Best-effort owner/name from the origin remote; None to let gh infer."""
    url = _git_out(repo_root, ["remote", "get-url", "origin"])
    return _url_to_nwo(url) if url else None


def _sweep_stale_locks():
    """Remove armed-locks older than STALE_LOCK_SECS (orphaned watchers)."""
    try:
        if not ARMED_DIR.is_dir():
            return
        now = time.time()
        for lock in ARMED_DIR.glob("*.lock"):
            try:
                if now - lock.stat().st_mtime > STALE_LOCK_SECS:
                    lock.unlink()
            except OSError:
                continue
    except OSError:
        return


def _lock_name(nwo, repo_root, key):
    """Collision-free lock filename. The digest hashes repo IDENTITY (nwo + repo_root)
    AND the full SHA-set key, so two repos with the same SHA set never collide (A-1)."""
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(repo_root).name)
    digest = hashlib.sha256(f"{nwo}\0{repo_root}\0{key}".encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}.lock"


def _arm(repo_root, branch, target_shas, armed_at, nwo, broad, mode, selector="-"):
    """Write the idempotency lock and spawn the detached watcher. Returns bool.

    The lock digest keys on repo identity + the sorted SHA set + mode + selector, so
    two concurrent PR merges (distinct selectors) from the same HEAD never collide.
    The watcher is spawned with the unified 9-positional contract (…, mode, selector)
    and removes its own lock on exit.
    """
    try:
        ARMED_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    nwo_arg = nwo or "-"
    shas_csv = ",".join(sorted(target_shas))
    lock_key = f"{shas_csv}|{mode}|{selector}"
    lock = ARMED_DIR / _lock_name(nwo_arg, repo_root, lock_key)
    if lock.exists():
        return False  # already armed for this target: idempotent no-op
    try:
        armed_count = len(list(ARMED_DIR.glob("*.lock")))
    except OSError:
        armed_count = 0
    if armed_count >= MAX_ARMED_WATCHERS:
        return False  # too many concurrent watchers already: do not pile on
    if not WATCHER.exists():
        return False
    try:
        lock.write_text(json.dumps({
            "repo_root": repo_root, "branch": branch, "target_shas": sorted(target_shas),
            "armed_at": armed_at, "nwo": nwo_arg, "broad": broad, "mode": mode,
            "selector": selector,
            "lock_written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }), encoding="utf-8")
    except OSError:
        return False
    try:
        devnull = open(os.devnull, "wb")
        subprocess.Popen(
            [sys.executable, str(WATCHER), repo_root, branch, shas_csv, str(lock),
             nwo_arg, armed_at, broad, mode, selector],
            stdin=subprocess.DEVNULL, stdout=devnull, stderr=devnull,
            start_new_session=True, cwd=repo_root,
        )
    except (OSError, ValueError):
        try:
            lock.unlink()
        except OSError:
            pass
        return False
    return True


def main():
    if os.environ.get("CT_CI_WATCH_DISABLE") == "1":
        return
    try:
        payload = sys.stdin.read()
    except OSError:
        payload = ""
    try:
        event = json.loads(payload) if payload else {}
    except (json.JSONDecodeError, ValueError):
        event = {}
    if event.get("tool_name") != "Bash":
        return
    command = ""
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command", "") or ""
    if not command:
        return
    _sweep_stale_locks()
    trigger = _classify_trigger(command)
    if trigger is None:
        return
    mode = MODE_MERGE if trigger == "pr-merge" else MODE_PUSH
    target = _resolve_target(command, mode)
    if target is None:
        return  # not in a git repo / cannot resolve: nothing to watch
    repo_root, branch, target_shas, armed_at, nwo, broad, resolved_mode, selector = target
    _arm(repo_root, branch, target_shas, armed_at, nwo, broad, resolved_mode, selector)
    # Side-effect-only handler: emit no decision, never block the push.


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - arming must never block a push or crash dispatch
        pass
    sys.exit(0)
