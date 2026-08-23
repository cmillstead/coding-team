#!/usr/bin/env python3
"""PostToolUse/Bash handler: arm the CI watcher after a CI-triggering command.

Invoked by posttooluse-dispatcher.py in its tool_name==Bash branch. Detects a
push, a PR-create, or a PR-merge, resolves what the watcher must attach to, and
fire-and-forgets a DETACHED ci-watcher.py process. Returns in well under 100ms
and NEVER blocks the push (side-effect-only; emits no decision).

Two attach strategies, keyed on the trigger type (see harness decision
ci-watch-merge-staleness-2026-07-09):

  - push / pr-create -> mode "push". Resolve the LOCAL HEAD sha + current
    branch; the watcher matches the Actions run by that headSha. Correct because
    you send HEAD and the run is FOR HEAD.

  - pr-merge -> mode "merge". Local HEAD is STALE at merge time: the merge
    commit is created on the REMOTE base branch and local main has not been
    pulled, so it still points at the pre-merge sha. Matching that stale headSha
    attaches to the OLD (pre-merge) run and false-alarms its old conclusion.
    Instead we capture the arm TIMESTAMP (UTC ISO-8601 Z) and resolve the merge
    BASE branch (the PR baseRefName when a PR number is in the command, else the
    repo default branch); the watcher selects the NEWEST run on that base branch
    created STRICTLY AFTER the arm time, ignoring any pre-arm/stale run.

Structural replacement for the memory note feedback_monitor_ci_after_push.md,
which depended on Claude remembering to watch CI. See harness decision
post-push-ci-watch-2026-07-09.

Idempotency + cleanup:
  - Armed-lock ~/.claude/ci-watch/armed/<repo>-<key>.lock prevents double-arming
    the same target. For push/pr-create the key is the HEAD sha; for pr-merge
    (where the local sha is stale/shared across merges) the key is the arm
    timestamp. The watcher removes its own lock on exit.
  - On each invocation, stale armed-locks older than STALE_LOCK_SECS (orphaned
    watchers) are swept.

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

# Trigger modes passed to the watcher as its 6th positional arg.
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


def _classify_trigger(command):
    """Classify a CI-triggering command as push, pr-create, or pr-merge.

    Returns one of "push", "pr-create", "pr-merge", or None (not CI-triggering).
    The gh path is glued-separator-aware and skips option VALUES (so `-R o/n`
    before the subcommand doesn't shift the positional grammar); push detection
    reuses the shared git parser. A push and a pr-create both take the headSha
    path (MODE_PUSH); only a pr-merge takes the merge path (MODE_MERGE).
    """
    tokens = _gh_tokens(command)
    for index, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] != "gh":
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
    the glued-separator-aware tokenizer and skips gh option VALUES."""
    tokens = _gh_tokens(command)
    for index, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] != "gh":
            continue
        positionals = _gh_positionals(_gh_segment(tokens, index))
        if positionals[:2] == ["pr", "merge"]:
            return positionals[2] if len(positionals) > 2 else None
    return None


def _gh_repo_override(command):
    """The `-R`/`--repo` owner/name override on a gh command, or None."""
    tokens = _gh_tokens(command)
    for index, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] != "gh":
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


def _merge_commit_sha(repo_root, nwo, selector):
    """The merge commit SHA of the PR via `gh pr view <selector> --json mergeCommit`,
    or None (not yet merged / --auto / gh error)."""
    cmd = ["gh", "pr", "view"]
    if selector:
        cmd.append(str(selector))
    cmd += ["--json", "mergeCommit"]
    if nwo:
        cmd += ["--repo", nwo]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=6, cwd=repo_root)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    commit = data.get("mergeCommit") if isinstance(data, dict) else None
    if isinstance(commit, dict) and isinstance(commit.get("oid"), str) and commit["oid"]:
        return commit["oid"]
    return None


def _is_ci_triggering(command):
    """True if the bash command triggers GitHub Actions (push / PR create / merge)."""
    return _classify_trigger(command) is not None


def _default_branch(repo_root, nwo):
    """Resolve the repo default branch (best-effort). None if unresolvable.

    Prefers the local remote HEAD symbolic ref (no network); falls back to
    gh repo view --json defaultBranchRef.
    """
    ref = _git_out(repo_root, ["symbolic-ref", "refs/remotes/origin/HEAD"])
    if ref:
        # e.g. refs/remotes/origin/main -> main
        name = ref.rsplit("/", 1)[-1]
        if name:
            return name
    return _gh_default_branch(repo_root, nwo)


def _gh_default_branch(repo_root, nwo):
    """gh repo view --json defaultBranchRef -> branch name, or None."""
    cmd = ["gh", "repo", "view", "--json", "defaultBranchRef"]
    if nwo:
        cmd += ["--repo", nwo]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=6,
                           cwd=repo_root)
    except (subprocess.SubprocessError, OSError):
        return None
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    ref = data.get("defaultBranchRef") if isinstance(data, dict) else None
    if isinstance(ref, dict):
        name = ref.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _pr_base_branch(repo_root, nwo, pr_number):
    """gh pr view <n> --json baseRefName -> base branch name, or None."""
    cmd = ["gh", "pr", "view", str(pr_number), "--json", "baseRefName"]
    if nwo:
        cmd += ["--repo", nwo]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=6,
                           cwd=repo_root)
    except (subprocess.SubprocessError, OSError):
        return None
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict):
        name = data.get("baseRefName")
        if isinstance(name, str) and name:
            return name
    return None


_PUSH_VALUE_OPTS = frozenset({"-o", "--push-option", "--receive-pack", "--exec", "--recurse-submodules"})
_AMBIGUOUS_PUSH_FLAGS = frozenset({"--branches", "--mirror"})   # --mirror is precise-able but treat broad-safe


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
    """True when the push form cannot be precisely enumerated -> safe-broad watch."""
    parsed = _push_args(command)
    if parsed is None:
        return False
    _remote, refspecs, _all, _tags, _mirror = parsed
    if git_invocations is None:
        return True
    try:
        for _sub, args in git_invocations(command):
            if any(a in _AMBIGUOUS_PUSH_FLAGS for a in args):
                return True
    except Exception:  # noqa: BLE001
        return True
    for refspec in refspecs:
        if refspec in (":", "::") or "*" in refspec:
            return True
    return False


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

    Returns the 6-tuple (repo_root, branch, target_shas, armed_at, nwo, broad) or
    None. target_shas is a set of the pushed/merged SHAs (HEAD in broad mode); nwo
    is the repo the runs live in; broad is "1"/"0".
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

    if mode == MODE_MERGE:
        nwo = _gh_repo_override(command) or _nwo(repo_root)
        selector = _pr_selector(command)
        merge_sha = _merge_commit_sha(repo_root, nwo, selector)
        head = _sha_set(repo_root, ["HEAD"])
        if not merge_sha:
            # ambiguous / --auto / not-yet-merged -> safe-broad (never nothing).
            branch = (_pr_base_branch(repo_root, nwo, selector) if selector else None) \
                or _default_branch(repo_root, nwo) or "-"
            return repo_root, branch, head, armed_at, nwo, "1"
        base = (_pr_base_branch(repo_root, nwo, selector) if selector else None) \
            or _default_branch(repo_root, nwo) or "-"
        return repo_root, base, {merge_sha}, armed_at, nwo, "0"

    # MODE_PUSH (git push OR gh pr create). nwo = gh -R override, else the ACTUAL
    # pushed remote. Ambiguous forms -> safe-broad.
    nwo = _gh_repo_override(command) or _push_remote_nwo(repo_root, command)
    head = _sha_set(repo_root, ["HEAD"])
    if _is_ambiguous_push(command):
        branch = _git_out(repo_root, ["branch", "--show-current"]) or "-"
        return repo_root, branch, head, armed_at, nwo, "1"
    shas = _pushed_source_shas(repo_root, command) or head    # gh pr create -> HEAD (R3-2)
    if not shas:
        return None
    branch = _git_out(repo_root, ["branch", "--show-current"]) or "-"
    return repo_root, branch, shas, armed_at, nwo, "0"


def _repo_root_fallback(directory):
    return _git_out(directory, ["rev-parse", "--show-toplevel"], use_C=True)


def _git_out(where, args, use_C=True):
    """Run git in where, return stripped stdout or None."""
    cmd = ["git", "-C", where, *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except (subprocess.SubprocessError, OSError):
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    return out or None


def _nwo(repo_root):
    """Best-effort owner/name from the origin remote; None to let gh infer."""
    url = _git_out(repo_root, ["remote", "get-url", "origin"])
    if not url:
        return None
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        return None
    return m.group(1) + "/" + m.group(2)


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


def _arm(repo_root, branch, target_shas, armed_at, nwo, broad, mode):
    """Write the idempotency lock and spawn the detached watcher. Returns bool.

    The lock digest keys on repo identity + the full sorted SHA set, so concurrent
    watches on different repos (or different SHA sets) never collide. The watcher is
    spawned with the unified 7-positional contract and removes its own lock on exit.
    """
    try:
        ARMED_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    nwo_arg = nwo or "-"
    shas_csv = ",".join(sorted(target_shas))
    lock = ARMED_DIR / _lock_name(nwo_arg, repo_root, shas_csv)
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
            "lock_written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }), encoding="utf-8")
    except OSError:
        return False
    try:
        devnull = open(os.devnull, "wb")
        subprocess.Popen(
            [sys.executable, str(WATCHER), repo_root, branch, shas_csv, str(lock),
             nwo_arg, armed_at, broad],
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
    repo_root, branch, target_shas, armed_at, nwo, broad = target
    _arm(repo_root, branch, target_shas, armed_at, nwo, broad, mode)
    # Side-effect-only handler: emit no decision, never block the push.


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - arming must never block a push or crash dispatch
        pass
    sys.exit(0)
