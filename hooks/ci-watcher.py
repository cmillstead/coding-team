#!/usr/bin/env python3
"""Detached background CI watcher (Verify + Correct tier).

Spawned fire-and-forget by ci-watch-arm.py after a CI-triggering git/gh command.
Waits for the matching GitHub Actions run to complete, and on a GENUINE job
failure (a job that is NOT continue-on-error) fires a macOS desktop notification
AND writes a marker file that ci-watch-inject.py surfaces into the next Claude
turn. Runs as an independent process: it must NEVER block the push and NEVER
raise into the caller. All failures degrade to a clean silent exit. See harness
decisions post-push-ci-watch-2026-07-09 and ci-watch-merge-staleness-2026-07-09.

Run-selection depends on the arm MODE (6th positional arg):

  - mode "push" (push / pr-create): match the run whose headSha equals the
    just-sent HEAD sha. Correct because the run is FOR that HEAD.

  - mode "merge" (pr-merge): the local HEAD sha is STALE (the merge commit is
    made on the remote base branch; local main was not pulled), so headSha
    matching would attach to the OLD pre-merge run and false-alarm. Instead
    select the NEWEST run on the base branch whose createdAt is STRICTLY AFTER
    the arm timestamp (7th positional arg), ignoring any pre-arm/stale run.

Back-compat: a watcher spawned by an older arm (5 args, no mode/armed_at)
defaults to mode "push" and headSha matching.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
CI_WATCH_DIR = HOME / ".claude" / "ci-watch"
FAILURES_DIR = CI_WATCH_DIR / "failures"

RUN_APPEAR_CAP = 90
RUN_APPEAR_POLL = 6
POLL_INTERVAL = 15
WATCH_CAP = 20 * 60
GH_TIMEOUT = 30
PREFILTER_HOURS = 6  # coarse server floor to bound pagination — NOT the selection key
FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out"}

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


def _parse_iso_z(value):
    """Parse a GitHub ISO-8601 Z timestamp to an aware datetime, or None.

    Accepts "2026-07-09T15:55:26Z" (and the +00:00 variant). Returns None for
    missing / malformed / non-string input so callers can skip it safely.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _continue_on_error_jobs(repo_root):
    """Collect job keys marked continue-on-error: true across the repo workflows.

    Dependency-free line scan (no PyYAML: this runs detached under an unknown
    interpreter). Records the most recent jobs-level job key and, when a
    continue-on-error: true line appears more indented than that key, adds it.
    Scans every workflow file: a MISSED continue-on-error job would false-alert
    (the worse outcome), so we err toward catching them all. engram => security,
    guardrails.
    """
    ignore = set()
    wf_dir = Path(repo_root) / ".github" / "workflows"
    if not wf_dir.is_dir():
        return ignore
    job_key_re = re.compile(r"^(\s+)([A-Za-z0-9_-]+):\s*$")
    coe_true_re = re.compile(r"^\s+continue-on-error:\s*true\s*(#.*)?$")
    files = sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml"))
    for wf in files:
        try:
            lines = wf.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        in_jobs = False
        jobs_indent = 0
        current_job = None
        current_job_indent = 0
        for raw in lines:
            line = raw.replace(chr(9), "  ")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if not in_jobs:
                if stripped == "jobs:":
                    in_jobs = True
                    jobs_indent = indent
                continue
            if indent <= jobs_indent and stripped.endswith(":") and stripped != "jobs:":
                break
            m = job_key_re.match(line)
            if m and len(m.group(1)) == jobs_indent + 2:
                current_job = m.group(2)
                current_job_indent = indent
                continue
            if current_job and coe_true_re.match(line) and indent > current_job_indent:
                ignore.add(current_job)
    return ignore


def _find_run_id(head_sha, branch, nwo, cwd):
    """Poll gh run list until a run for head_sha appears. None on timeout.

    Used for mode push (push / pr-create), where the run is FOR the just-sent
    HEAD sha.
    """
    deadline = time.time() + RUN_APPEAR_CAP
    while time.time() < deadline:
        out = _gh(
            ["run", "list", "--branch", branch, "--limit", "20",
             "--json", "databaseId,headSha,status"],
            nwo, cwd,
        )
        if out:
            try:
                runs = json.loads(out)
            except (json.JSONDecodeError, ValueError):
                runs = []
            for run in runs:
                if str(run.get("headSha", "")) == head_sha:
                    return int(run["databaseId"])
        time.sleep(RUN_APPEAR_POLL)
    return None


def _find_run_after(branch, armed_at, nwo, cwd):
    """Poll gh run list for the NEWEST run on branch created after armed_at.

    Used for mode merge. armed_at is a UTC ISO-8601 Z timestamp captured at arm
    time. Any run whose createdAt is at/before armed_at is a pre-merge/stale run
    and is IGNORED. Among the post-arm runs the newest by createdAt wins (the
    merge-commit run). Returns its databaseId, or None on timeout / no post-arm
    run yet. If armed_at cannot be parsed, returns None (fail safe: no false
    attach) rather than degrading to headSha matching on a stale sha.
    """
    armed_dt = _parse_iso_z(armed_at)
    if armed_dt is None:
        return None
    deadline = time.time() + RUN_APPEAR_CAP
    while time.time() < deadline:
        out = _gh(
            ["run", "list", "--branch", branch, "--limit", "20",
             "--json", "databaseId,headSha,status,createdAt"],
            nwo, cwd,
        )
        if out:
            try:
                runs = json.loads(out)
            except (json.JSONDecodeError, ValueError):
                runs = []
            best_id = None
            best_dt = None
            for run in runs:
                created = _parse_iso_z(run.get("createdAt"))
                if created is None or created <= armed_dt:
                    continue  # pre-arm / stale / unparseable -> ignore
                if best_dt is None or created > best_dt:
                    best_dt = created
                    try:
                        best_id = int(run["databaseId"])
                    except (KeyError, TypeError, ValueError):
                        best_id = None
            if best_id is not None:
                return best_id
        time.sleep(RUN_APPEAR_POLL)
    return None


def _poll_to_completion(run_id, nwo, cwd, deadline):
    """Poll gh run view until status==completed or deadline. Return final view."""
    while time.time() < deadline:
        out = _gh(
            ["run", "view", str(run_id), "--json", "status,conclusion,jobs"],
            nwo, cwd,
        )
        if out:
            try:
                view = json.loads(out)
            except (json.JSONDecodeError, ValueError):
                view = None
            if view and view.get("status") == "completed":
                return view
        time.sleep(POLL_INTERVAL)
    return None


def _genuine_failures(view, ignore):
    """Return jobs that genuinely failed (excluding continue-on-error jobs)."""
    failed = []
    for job in view.get("jobs", []):
        name = job.get("name", "")
        if name in ignore:
            continue
        if job.get("conclusion") in FAILED_CONCLUSIONS:
            failed.append(job)
    return failed


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


def _write_marker(run_id, nwo, branch, failed_jobs):
    """Write a failure marker JSON that ci-watch-inject.py surfaces + consumes."""
    try:
        FAILURES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    repo_disp = nwo or "(cwd repo)"
    url = failed_jobs[0].get("url", "") if failed_jobs else ""
    run_url = re.sub(r"/job/\d+$", "", url) if url else ""
    marker = {
        "run_id": run_id,
        "repo": repo_disp,
        "branch": branch,
        "run_url": run_url,
        "failed_jobs": [
            {"name": j.get("name", ""), "conclusion": j.get("conclusion", ""),
             "url": j.get("url", "")}
            for j in failed_jobs
        ],
        "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    marker_path = FAILURES_DIR / (str(run_id) + ".json")
    try:
        marker_path.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    except OSError:
        pass


def main():
    args = sys.argv[1:]
    if len(args) < 5:
        return
    repo_root, branch, head_sha, armed_lock, nwo_arg = args[:5]
    # Args 6-7 (mode, armed_at) are optional for back-compat with an older arm
    # that spawned only 5 args; absence defaults to headSha matching (push).
    mode = args[5] if len(args) >= 6 and args[5] else MODE_PUSH
    armed_at = args[6] if len(args) >= 7 else "-"
    nwo = None if nwo_arg == "-" else nwo_arg
    cwd = repo_root if os.path.isdir(repo_root) else os.getcwd()
    armed_lock_path = Path(armed_lock)
    try:
        deadline = time.time() + WATCH_CAP
        if mode == MODE_MERGE:
            # Base-branch + post-arm-timestamp selection (stale local sha ignored).
            run_id = _find_run_after(branch, armed_at, nwo, cwd)
        else:
            run_id = _find_run_id(head_sha, branch, nwo, cwd)
        if run_id is None:
            return  # no workflow / no matching run: clean silent exit
        view = _poll_to_completion(run_id, nwo, cwd, deadline)
        if view is None:
            return  # hit the 20-min cap without completion: give up silently
        ignore = _continue_on_error_jobs(repo_root)
        failed = _genuine_failures(view, ignore)
        if not failed:
            return  # green (or only continue-on-error jobs red): nothing to do
        names = ", ".join(j.get("name", "?") for j in failed)
        repo_label = nwo or "repo"
        message = repo_label + " @ " + branch + ": " + names
        _notify_desktop("CI FAILED - action needed", message)
        _write_marker(run_id, nwo, branch, failed)
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
