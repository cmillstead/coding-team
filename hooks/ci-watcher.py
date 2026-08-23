#!/usr/bin/env python3
"""Detached bounded CI watcher (Verify + Correct tier).

Spawned fire-and-forget by ci-watch-arm.py after a CI-triggering git/gh command.
Within a bounded (~20-minute) window it watches the GitHub Actions runs it can
see for the pushed/merged SHA(s) and, on any OBSERVED run whose run-level
conclusion is not benign (see NON_ALERTING), fires a macOS desktop notification
AND durably writes a marker file that ci-watch-inject.py surfaces into the next
Claude turn. Runs as an independent process: it must NEVER block the push and
NEVER raise into the caller. All failures degrade to a clean silent exit.

Bounded contract: it faithfully reports GitHub's run-level conclusion for any run
it OBSERVES (no workflow-YAML parsing) — never suppressing/mislabelling an
observed failure and never reporting a false green. Runs that first appear,
re-run, or chain AFTER the window are out of scope (unseen, never green).

Arg contract (9 positional):
  repo_root branch target_shas_csv lock_path nwo armed_at broad mode selector
where target_shas_csv is the sorted pushed SHAs (for a merge it is only the local
HEAD lock-anchor — the watcher resolves the real merge-commit SHA from `selector`),
nwo is the repo the runs live in, armed_at is the ISO-8601 Z arm time (the recency
guard for completed runs), broad is "1"/"0", mode is "push"/"merge", and selector
is the PR selector for a merge ("-" otherwise). Args 8-9 are optional for
back-compat (absent -> mode "push").
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CI_WATCH_DIR = HOME / ".claude" / "ci-watch"
FAILURES_DIR = CI_WATCH_DIR / "failures"
# uid-scoped fallback under the temp root: a shared world-writable /tmp path read
# in-process every prompt is a plant target (FIFO hang / symlink / poisoned marker),
# so the dir name carries the uid and is created 0o700 (owner-only). The inject
# read side additionally rejects symlinks/non-regular/foreign/oversized files.
FALLBACK_DIR = Path(tempfile.gettempdir()) / f"ci-watch-failures-{os.getuid()}"

POLL_INTERVAL = 15
WATCH_CAP = 20 * 60
GRACE_AFTER_TERMINAL = 90
GH_TIMEOUT = 30
PREFILTER_HOURS = 6  # coarse server floor to bound pagination — NOT the selection key
MARKER_WRITE_RETRIES = 2

MODE_PUSH = "push"
MODE_MERGE = "merge"

# GitHub's run conclusion already folds job-level continue-on-error into the result,
# so the run conclusion is the whole observed-failure decision. Only success/neutral/
# skipped are benign. cancelled/stale ALERT (a cancelled run can hide a failed job).
# Anything not in NON_ALERTING (incl. unknown/None) alerts — fail toward alerting.
NON_ALERTING = frozenset({"success", "neutral", "skipped"})


def _is_alerting_conclusion(conclusion):
    return conclusion not in NON_ALERTING


def _gh(args, nwo, cwd):
    """Run a gh command, returning stdout, or None on any error/timeout."""
    cmd = ["gh", *args]
    if nwo:
        cmd += ["--repo", nwo]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=cwd,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _gh_json(args, nwo, cwd):
    """Run a gh command and return its parsed JSON (dict/list), or None on any
    error / non-JSON output. Dedupes the gh-json boilerplate shared by the merge
    helpers below."""
    out = _gh(args, nwo, cwd)
    if out is None:
        return None
    try:
        return json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return None


def _merge_commit_sha(cwd, nwo, selector):
    """The merge-commit SHA of the PR via `gh pr view <selector> --json mergeCommit`,
    or None (not yet merged / --auto / gh error). Runs in the DETACHED watcher, never
    in arm, so the user's turn is never blocked on this network call."""
    args = ["pr", "view"]
    if selector:
        args.append(str(selector))
    args += ["--json", "mergeCommit"]
    data = _gh_json(args, nwo, cwd)
    commit = data.get("mergeCommit") if isinstance(data, dict) else None
    if isinstance(commit, dict) and isinstance(commit.get("oid"), str) and commit["oid"]:
        return commit["oid"]
    return None


def _pr_base_branch(cwd, nwo, selector):
    """gh pr view <selector> --json baseRefName -> base branch name, or None."""
    args = ["pr", "view"]
    if selector:
        args.append(str(selector))
    args += ["--json", "baseRefName"]
    data = _gh_json(args, nwo, cwd)
    if isinstance(data, dict):
        name = data.get("baseRefName")
        if isinstance(name, str) and name:
            return name
    return None


def _gh_default_branch(cwd, nwo):
    """gh repo view --json defaultBranchRef -> branch name, or None."""
    data = _gh_json(["repo", "view", "--json", "defaultBranchRef"], nwo, cwd)
    ref = data.get("defaultBranchRef") if isinstance(data, dict) else None
    if isinstance(ref, dict):
        name = ref.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _prefilter_floor(armed_at):
    """Coarse `created >=` floor (armed_at - PREFILTER_HOURS) to bound the API result
    set. Selection correctness is head_sha + status + `updated_at`, not this floor."""
    try:
        dt = datetime.fromisoformat(armed_at.replace("Z", "+00:00")) - timedelta(hours=PREFILTER_HOURS)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return armed_at


def _observed_this_watch(run, armed_at):
    """Bounded recency guard: an in-flight (queued/in_progress) run is ALWAYS this
    trigger's concern. A completed run is skipped ONLY if it completed BEFORE the
    watch began (updated_at < armed_at) — i.e. it is a prior result, not ours.
    Unknown updated_at -> watch (fail toward alerting on an observed run)."""
    if run.get("status") != "completed":
        return True
    updated = str(run.get("updated_at", ""))
    if not updated:
        return True
    return updated >= armed_at


def _parse_runs(raw_runs):
    return [
        {"id": r.get("id") if "id" in r else r.get("databaseId"),
         "head_sha": r.get("head_sha") or r.get("headSha"),
         "status": r.get("status"), "conclusion": r.get("conclusion"),
         "name": r.get("name") or r.get("workflowName"),
         "created_at": r.get("created_at") or r.get("createdAt"),
         "updated_at": r.get("updated_at") or r.get("updatedAt")}
        for r in raw_runs
    ]


def _gh_api_runs(query, cwd):
    """Paginated NDJSON of runs via `gh api --paginate --jq '.workflow_runs[]'`, or None."""
    try:
        result = subprocess.run(["gh", "api", "--paginate", "--jq", ".workflow_runs[]", query],
                                capture_output=True, text=True, timeout=GH_TIMEOUT, cwd=cwd)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return _parse_runs(rows)


def _runs_for_sha(head_sha, armed_at, nwo, cwd):
    """Runs whose head commit == head_sha. Server-side head_sha filter + coarse
    created prefilter; fallback to `gh run list` (capped 200, client-filtered)."""
    if nwo:
        query = (f"repos/{nwo}/actions/runs?head_sha={head_sha}"
                 f"&created=%3E%3D{_prefilter_floor(armed_at)}&per_page=100")
        runs = _gh_api_runs(query, cwd)
        if runs is not None:
            return runs
    out = _gh(["run", "list", "-L", "200", "--json",
               "databaseId,headSha,status,conclusion,createdAt,updatedAt,workflowName"], nwo, cwd)
    if not out:
        return []
    try:
        rows = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return []
    return [r for r in _parse_runs(rows) if r["head_sha"] == head_sha]


def _active_runs(nwo, armed_at, cwd):
    """Safe-broad discovery: recent runs for the repo (no head_sha filter). Used when
    the pushed SHA can't be pinned — watch what's active/recent rather than nothing."""
    if not nwo:
        return []
    query = f"repos/{nwo}/actions/runs?created=%3E%3D{_prefilter_floor(armed_at)}&per_page=100"
    return _gh_api_runs(query, cwd) or []


def _failed_job_names(run_id, nwo, cwd):
    """Enrichment only: the names of failed jobs for run_id (never the alert
    decision, which is the run conclusion). Empty on any error."""
    out = _gh(["run", "view", str(run_id), "--json", "jobs"], nwo, cwd)
    if not out:
        return []
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return []
    return [j.get("name", "") for j in data.get("jobs", []) if j.get("conclusion") == "failure"]


def _notify_desktop(title, message):
    """Fire a macOS desktop notification via osascript. Best-effort; never raises."""
    script = (
        "display notification " + json.dumps(message)
        + " with title " + json.dumps(title)
        + " sound name " + json.dumps("Basso")
    )
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        pass


def _write_marker(run, nwo, branch, failed_jobs):
    """Durably publish a failure marker. Tries the primary dir (with a retry), then a
    system-temp fallback dir; atomic within each (temp + os.replace). Returns True if
    EITHER succeeds; False only if BOTH fail (caller then fires a last-resort notify).
    A detected failure is never silently lost."""
    try:
        run_id = int(run.get("id"))   # coerce: the filename is str(run_id) — never a
    except (TypeError, ValueError):   # traversal / injection from an attacker-shaped id.
        return False
    marker = {
        "run_id": run_id, "repo": nwo or "(cwd repo)", "branch": branch,
        "workflow": run.get("name", ""), "conclusion": run.get("conclusion", ""),
        "run_url": f"https://github.com/{nwo}/actions/runs/{run_id}" if nwo else "",
        "failed_jobs": failed_jobs,
        "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    payload = json.dumps(marker, indent=2)
    targets = [FAILURES_DIR] * (1 + MARKER_WRITE_RETRIES) + [FALLBACK_DIR]
    for target in targets:
        try:
            if target == FALLBACK_DIR:
                # The fallback lives in a shared temp root: create it owner-only and
                # enforce 0o700 even if it pre-exists. A dir we cannot own (planted by
                # another uid) fails the chmod -> we do NOT write into it (fail closed).
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(target, 0o700)
            else:
                target.mkdir(parents=True, exist_ok=True)
            tmp_path = target / (str(run_id) + ".json.tmp")
            final_path = target / (str(run_id) + ".json")
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, final_path)
            return True
        except OSError:
            continue
    return False


def main():
    args = sys.argv[1:]
    if len(args) < 7:
        return
    repo_root, branch, shas_csv, armed_lock, nwo_arg, armed_at, broad_arg = args[:7]
    mode = args[7] if len(args) >= 8 and args[7] else MODE_PUSH
    selector = args[8] if len(args) >= 9 else "-"
    nwo = None if nwo_arg == "-" else nwo_arg
    broad = broad_arg == "1"
    cwd = repo_root if os.path.isdir(repo_root) else os.getcwd()
    target_shas = [s for s in shas_csv.split(",") if s]
    armed_lock_path = Path(armed_lock)
    try:
        if mode == MODE_MERGE:
            # The gh-dependent merge resolution happens HERE (detached), never in
            # arm, so arm stays local-git-only and sub-100ms.
            sel = None if selector in ("-", "") else selector
            base = _pr_base_branch(cwd, nwo, sel) or _gh_default_branch(cwd, nwo)
            if base:
                branch = base
            merge_sha = _merge_commit_sha(cwd, nwo, sel)
            if merge_sha:
                target_shas = [merge_sha]
                broad = False
            else:
                # not-yet-merged / --auto: the local HEAD is the STALE pre-merge sha,
                # so watch a safe-broad set instead of matching it.
                target_shas = []
                broad = True
        if not target_shas and not broad:
            return
        deadline = time.time() + WATCH_CAP
        seen_ids = set()
        observed_shas = set()
        terminal_since = None
        while time.time() < deadline:
            raw = []
            for sha in target_shas:
                raw.extend(_runs_for_sha(sha, armed_at, nwo, cwd))
            if broad:
                raw.extend(_active_runs(nwo, armed_at, cwd))
            in_window = [r for r in raw if _observed_this_watch(r, armed_at)]  # bounded predicate
            by_id = {r["id"]: r for r in in_window if r.get("id") is not None}  # run-id dedup
            runs = list(by_id.values())
            if set(by_id) - seen_ids:                       # a NEW run appeared
                seen_ids |= set(by_id)
                terminal_since = None                       # reset grace clock
            observed_shas |= {r["head_sha"] for r in runs if r.get("head_sha") in target_shas}
            for run in runs:                                # round-robin; emit first failure
                if run.get("status") == "completed" and _is_alerting_conclusion(run.get("conclusion")):
                    failed = _failed_job_names(run.get("id"), nwo, cwd)
                    label = nwo or "repo"
                    _notify_desktop("CI FAILED - action needed",
                                    f"{label} @ {branch}: {run.get('name') or 'run'} ({run.get('conclusion')})")
                    if not _write_marker(run, nwo, branch, failed):   # A-4 durable
                        _notify_desktop("CI FAILED (marker write failed)",
                                        f"{label}: inspect gh run {run.get('id')} manually")
                    return
            # Multi-SHA: don't start the exit clock until every pushed SHA is observed
            # (broad mode can't assert per-SHA completeness, so it exits on drain+grace).
            shas_complete = broad or observed_shas >= set(target_shas)
            all_terminal = shas_complete and bool(runs) and all(r.get("status") == "completed" for r in runs)
            if all_terminal:
                if terminal_since is None:
                    terminal_since = time.time()
                elif time.time() - terminal_since > GRACE_AFTER_TERMINAL:
                    return
            else:
                terminal_since = None
            time.sleep(POLL_INTERVAL)
    finally:
        try:
            armed_lock_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - a detached watcher must never surface a crash
        sys.exit(0)
