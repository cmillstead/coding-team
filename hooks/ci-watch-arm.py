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
    from _lib.git import resolve_command_target_dir, resolve_repo_root
except Exception:  # noqa: BLE001 - handler must never crash the dispatcher
    resolve_command_target_dir = None
    resolve_repo_root = None

HOME = Path(os.path.expanduser("~"))
CI_WATCH_DIR = HOME / ".claude" / "ci-watch"
ARMED_DIR = CI_WATCH_DIR / "armed"
WATCHER = Path(__file__).resolve().parent / "ci-watcher.py"
STALE_LOCK_SECS = 30 * 60

# Trigger modes passed to the watcher as its 6th positional arg.
MODE_PUSH = "push"
MODE_MERGE = "merge"


def _classify_trigger(command):
    """Classify a CI-triggering command as push, pr-create, or pr-merge.

    Returns one of "push", "pr-create", "pr-merge", or None (not CI-triggering).
    A push and a pr-create both take the headSha-match path (MODE_PUSH); only a
    pr-merge takes the timestamp/base-branch path (MODE_MERGE).
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for i, tok in enumerate(tokens):
        base = tok.rsplit("/", 1)[-1]
        rest = tokens[i + 1:]
        nonflag = [t for t in rest if not t.startswith("-")]
        if base == "git" and nonflag[:1] == ["push"]:
            return "push"
        if base == "gh" and nonflag[:2] == ["pr", "create"]:
            return "pr-create"
        if base == "gh" and nonflag[:2] == ["pr", "merge"]:
            return "pr-merge"
    return None


def _pr_number(command):
    """Extract the PR number argument from a gh pr merge <n> command, or None.

    The first non-flag token after the pr merge subcommand that is all digits is
    the PR number. A merge with no number (current-branch PR) yields None.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for i, tok in enumerate(tokens):
        base = tok.rsplit("/", 1)[-1]
        rest = tokens[i + 1:]
        nonflag = [t for t in rest if not t.startswith("-")]
        if base == "gh" and nonflag[:2] == ["pr", "merge"]:
            for t in nonflag[2:]:
                if t.isdigit():
                    return t
            return None
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


def _resolve_target(command, mode):
    """Resolve what the watcher must attach to for command under mode.

    Returns (repo_root, branch, head_sha, armed_at) or None.

    For MODE_PUSH the branch is the current local branch and head_sha is the
    local HEAD sha (the watcher matches by headSha). armed_at is "-" (unused).

    For MODE_MERGE the branch is the merge BASE branch (PR baseRefName if a PR
    number is present, else the repo default branch), head_sha is "-" (the local
    sha is stale and MUST NOT be used), and armed_at is the current UTC ISO-8601
    timestamp (the watcher selects the newest run created after it).
    """
    if resolve_command_target_dir is None or resolve_repo_root is None:
        target_dir = os.getcwd()
        repo_root = _repo_root_fallback(target_dir)
    else:
        target_dir = resolve_command_target_dir(command)
        repo_root = resolve_repo_root(target_dir) or _repo_root_fallback(target_dir)
    if not repo_root:
        return None

    if mode == MODE_MERGE:
        nwo = _nwo(repo_root)
        base = None
        pr_number = _pr_number(command)
        if pr_number is not None:
            base = _pr_base_branch(repo_root, nwo, pr_number)
        if not base:
            base = _default_branch(repo_root, nwo)
        if not base:
            return None
        armed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return repo_root, base, "-", armed_at

    # MODE_PUSH: local HEAD sha + current branch (unchanged, correct path).
    branch = _git_out(repo_root, ["branch", "--show-current"])
    head_sha = _git_out(repo_root, ["rev-parse", "HEAD"])
    if not branch or not head_sha:
        return None
    return repo_root, branch, head_sha, "-"


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


def _lock_name(repo_root, key):
    """Lock filename slug from the repo name and an idempotency key.

    key is the HEAD sha (push/pr-create) or the arm timestamp (pr-merge). It is
    sanitized to filesystem-safe characters and truncated so two distinct merges
    (distinct arm timestamps) never collide on one lock.
    """
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(repo_root).name)
    key_slug = re.sub(r"[^A-Za-z0-9]", "", key)[:14]
    return slug + "-" + key_slug + ".lock"


def _arm(repo_root, branch, head_sha, armed_at, mode):
    """Write the idempotency lock and spawn the detached watcher. Returns bool."""
    try:
        ARMED_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    # Idempotency key: sha for push/pr-create, arm timestamp for merge (the sha
    # is stale and shared across merges, so it cannot key a merge lock).
    key = armed_at if mode == MODE_MERGE else head_sha
    lock = ARMED_DIR / _lock_name(repo_root, key)
    if lock.exists():
        return False  # already armed for this target: idempotent no-op
    if not WATCHER.exists():
        return False
    nwo = _nwo(repo_root) or "-"
    try:
        lock.write_text(json.dumps({
            "repo_root": repo_root, "branch": branch, "head_sha": head_sha,
            "mode": mode, "armed_at": armed_at,
            "lock_written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }), encoding="utf-8")
    except OSError:
        return False
    try:
        devnull = open(os.devnull, "wb")
        subprocess.Popen(
            [sys.executable, str(WATCHER), repo_root, branch, head_sha,
             str(lock), nwo, mode, armed_at],
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
    repo_root, branch, head_sha, armed_at = target
    _arm(repo_root, branch, head_sha, armed_at, mode)
    # Side-effect-only handler: emit no decision, never block the push.


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - arming must never block a push or crash dispatch
        pass
    sys.exit(0)
