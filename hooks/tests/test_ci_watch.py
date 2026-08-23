"""Real-implementation tests. No mocks: gh is a real stub executable on PATH;
timing/dirs via module-attribute assignment. One autouse fixture restores
os.environ (incl. PATH), cwd, and mutated module attrs."""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time

import pytest

from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent


def _load(basename, modname):
    spec = importlib.util.spec_from_file_location(modname, HOOKS_DIR / basename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ARM = _load("ci-watch-arm.py", "ci_watch_arm")
WATCHER = _load("ci-watcher.py", "ci_watcher")
INJECT = _load("ci-watch-inject.py", "ci_watch_inject")
POD = _load("posttooluse-dispatcher.py", "ci_watch_pod")
PD = _load("prompt-dispatcher.py", "ci_watch_pd")
WATCHER_PATH = HOOKS_DIR / "ci-watcher.py"

_SNAPSHOT = {
    ARM: ("CI_WATCH_DIR", "ARMED_DIR", "WATCHER", "STALE_LOCK_SECS"),
    WATCHER: ("CI_WATCH_DIR", "FAILURES_DIR", "FALLBACK_DIR", "POLL_INTERVAL",
              "WATCH_CAP", "GRACE_AFTER_TERMINAL"),
    INJECT: ("FAILURES_DIR", "FALLBACK_DIR"),
}


@pytest.fixture(scope="session", autouse=True)
def _stub_desktop_notifier(tmp_path_factory):
    """Put a no-op `osascript` on PATH for the WHOLE session so the watcher's
    _notify_desktop never fires a REAL macOS desktop notification during tests.
    A real on-PATH stub executable (not a mock/patch): write-guard compliant.
    Session-scoped + autouse so it is applied before the per-function
    _restore_state fixture snapshots os.environ, hence inherited by every test."""
    bin_dir = tmp_path_factory.mktemp("notify-stub")
    osascript = bin_dir / "osascript"
    osascript.write_text("#!/bin/sh\nexit 0\n")
    osascript.chmod(osascript.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}" + os.environ["PATH"]
    yield


@pytest.fixture(autouse=True)
def _restore_state():
    env = dict(os.environ)
    cwd = os.getcwd()
    saved = {(m, n): getattr(m, n, None) for m, names in _SNAPSHOT.items() for n in names}
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(env)
        os.chdir(cwd)
        for (mod, name), value in saved.items():
            setattr(mod, name, value)


def _nd(runs):
    return "\n".join(json.dumps(r) for r in runs)   # mimics `gh api --jq '.workflow_runs[]'`


def stub_gh(bin_dir, *, api_runs=None, runview="{}", prview="{}"):
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "api.ndjson").write_text(_nd(api_runs or []))
    (bin_dir / "runview.json").write_text(runview)
    (bin_dir / "prview.json").write_text(prview)
    _emit_gh(bin_dir, sequenced=False)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}" + os.environ["PATH"]
    return bin_dir


def stub_gh_sequence(bin_dir, *, api_run_polls, runview="{}"):
    bin_dir.mkdir(parents=True, exist_ok=True)
    for i, runs in enumerate(api_run_polls):
        (bin_dir / f"api_{i}.ndjson").write_text(_nd(runs))
    (bin_dir / "runview.json").write_text(runview)
    (bin_dir / "count").write_text("0")
    _emit_gh(bin_dir, sequenced=True, npolls=len(api_run_polls))
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}" + os.environ["PATH"]
    return bin_dir


def _emit_gh(bin_dir, *, sequenced, npolls=0):
    gh = bin_dir / "gh"
    common = ("elif 'run' in a and 'view' in a: print((d/'runview.json').read_text())\n"
              "elif 'pr' in a and 'view' in a: print((d/'prview.json').read_text())\n"
              "else: print('{}')\n")
    if sequenced:
        body = ("import sys, pathlib\nd=pathlib.Path(__file__).resolve().parent; a=sys.argv[1:]\n"
                "if 'api' in a:\n"
                " c=int((d/'count').read_text() or '0')\n"
                f" idx=min(c,{npolls-1})\n"
                " (d/'count').write_text(str(c+1))\n"
                " print((d/f'api_{idx}.ndjson').read_text())\n" + common)
    else:
        body = ("import sys, pathlib\nd=pathlib.Path(__file__).resolve().parent; a=sys.argv[1:]\n"
                "if 'api' in a: print((d/'api.ndjson').read_text())\n" + common)
    gh.write_text("#!/usr/bin/env python3\n" + body)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    # A no-op osascript alongside gh so the watcher's _notify_desktop resolves the
    # stub (never a REAL macOS notification) even from this bin dir.
    osascript = bin_dir / "osascript"
    osascript.write_text("#!/bin/sh\nexit 0\n")
    osascript.chmod(osascript.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def init_repo(tmp_path, *, origin="git@github.com:o/n.git"):
    r = tmp_path / "repo"
    r.mkdir()
    env = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "-C", str(r), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(r), "remote", "add", "origin", origin], check=True)
    subprocess.run(["git", "-C", str(r), *env, "commit", "--allow-empty", "-qm", "base"], check=True)
    subprocess.run(["git", "-C", str(r), "branch", "-M", "feat/x"], check=True)
    return r, env


def divergent_repo(tmp_path):
    repo, env = init_repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), *env, "commit", "--allow-empty", "-qm", "m"], check=True)
    subprocess.run(["git", "-C", str(repo), "tag", "v1"], check=True)
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "feat/x"], check=True)
    subprocess.run(["git", "-C", str(repo), *env, "commit", "--allow-empty", "-qm", "f"], check=True)

    def sha(ref):
        return subprocess.run(["git", "-C", str(repo), "rev-parse", ref],
                              capture_output=True, text=True).stdout.strip()

    return repo, sha


def run_watcher_main(tmp_path, shas, *, nwo="o/n", armed_at="2000-01-01T00:00:00Z",
                     branch="feat/x", broad="0"):
    lock = tmp_path / "x.lock"
    lock.write_text("{}")
    argv = [str(WATCHER_PATH), str(tmp_path), branch, ",".join(shas), str(lock), nwo, armed_at, broad]
    old = sys.argv
    sys.argv = argv
    try:
        WATCHER.main()
    finally:
        sys.argv = old
    return lock


# --------------------------------------------------------------------------
# Task 2: alert on run conclusion (no YAML)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("conclusion,alert", [
    ("failure", True), ("timed_out", True), ("startup_failure", True), ("action_required", True),
    ("cancelled", True), ("stale", True), (None, True), ("brand_new", True),
    ("success", False), ("neutral", False), ("skipped", False),
])
def test_is_alerting_conclusion(conclusion, alert):
    assert WATCHER._is_alerting_conclusion(conclusion) is alert


# --------------------------------------------------------------------------
# Task 3: paginated head_sha discovery + bounded recency predicate
# --------------------------------------------------------------------------

def test_runs_for_sha_parses_ndjson_and_keeps_headsha(tmp_path):
    stub_gh(tmp_path / "bin", api_runs=[{"id": 1, "head_sha": "beef", "status": "completed",
            "conclusion": "failure", "name": "CI", "created_at": "t", "updated_at": "t"}])
    runs = WATCHER._runs_for_sha("beef", "2000-01-01T00:00:00Z", "o/n", str(tmp_path))
    assert runs[0]["id"] == 1 and runs[0]["head_sha"] == "beef" and runs[0]["conclusion"] == "failure"


def test_runs_for_sha_clean_when_gh_absent(tmp_path):
    empty = tmp_path / "e"
    empty.mkdir()
    os.environ["PATH"] = str(empty)
    assert WATCHER._runs_for_sha("beef", "2000-01-01T00:00:00Z", "o/n", str(tmp_path)) == []


@pytest.mark.parametrize("run,armed_at,keep", [
    ({"status": "in_progress", "updated_at": "1999-01-01T00:00:00Z"}, "2026-08-23T00:00:00Z", True),
    ({"status": "queued", "updated_at": ""}, "2026-08-23T00:00:00Z", True),
    ({"status": "completed", "updated_at": "2026-08-23T10:00:00Z"}, "2026-08-23T00:00:00Z", True),
    ({"status": "completed", "updated_at": "2020-01-01T00:00:00Z"}, "2026-08-23T00:00:00Z", False),
    ({"status": "completed", "updated_at": ""}, "2026-08-23T00:00:00Z", True),  # unknown -> watch
])
def test_observed_this_watch(run, armed_at, keep):
    assert WATCHER._observed_this_watch(run, armed_at) is keep


# --------------------------------------------------------------------------
# Task 4: the bounded watch loop (multi-SHA, safe-broad, grace, durable emit)
# --------------------------------------------------------------------------

def _use_dirs(tmp_path):
    WATCHER.FAILURES_DIR = tmp_path / "f"
    WATCHER.FALLBACK_DIR = tmp_path / "fb"
    INJECT.FAILURES_DIR = tmp_path / "f"
    INJECT.FALLBACK_DIR = tmp_path / "fb"
    return tmp_path / "f"


def _run(id, sha, status, concl, upd="2026-08-23T10:00:00Z"):
    return {"id": id, "head_sha": sha, "status": status, "conclusion": concl,
            "name": "W", "created_at": upd, "updated_at": upd}


def test_watcher_never_opens_workflow_files(tmp_path):  # R3-13 behavioral trap
    repo = tmp_path / "repo"
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("name: CI\njobs:\n  test:\n    runs-on: x\n")
    opened = []
    sys.addaudithook(lambda ev, a: opened.append(str(a[0]))
                     if ev == "open" and a and ".github/workflows" in str(a[0]) else None)
    WATCHER.FAILURES_DIR = tmp_path / "f"
    WATCHER.POLL_INTERVAL = 0
    WATCHER.WATCH_CAP = 0.05
    WATCHER.GRACE_AFTER_TERMINAL = 0
    stub_gh(tmp_path / "bin", api_runs=[{"id": 1, "head_sha": "beef", "status": "completed",
            "conclusion": "success", "name": "CI", "created_at": "t", "updated_at": "t"}])
    run_watcher_main(repo, ["beef"])
    assert opened == []


def test_main_green_then_red_same_sha_alerts(tmp_path):  # MANDATORY D2 falsifier
    d = _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.GRACE_AFTER_TERMINAL = 0
    stub_gh(tmp_path / "bin", api_runs=[_run(1, "beef", "completed", "success"),
            _run(2, "beef", "completed", "failure")],
            runview=json.dumps({"jobs": [{"name": "pytest", "conclusion": "failure"}]}))
    lock = run_watcher_main(tmp_path, ["beef"])
    m = [json.loads(p.read_text()) for p in d.glob("*.json")]
    assert len(m) == 1 and m[0]["run_id"] == 2 and not lock.exists()


def test_main_multi_sha_waits_for_all(tmp_path):  # never false-green on an unobserved SHA
    d = _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.GRACE_AFTER_TERMINAL = 0
    # poll1: only SHA-A observed (green, terminal); SHA-B has no run yet.
    # poll2: SHA-B appears RED. Must alert (exit clock must not have fired on poll1).
    stub_gh_sequence(tmp_path / "bin", api_run_polls=[
        [_run(1, "aaa", "completed", "success")],
        [_run(1, "aaa", "completed", "success"), _run(2, "bbb", "completed", "failure")]],
        runview=json.dumps({"jobs": []}))
    run_watcher_main(tmp_path, ["aaa", "bbb"])
    assert [json.loads(p.read_text())["run_id"] for p in d.glob("*.json")] == [2]


def test_main_late_chained_run_within_grace(tmp_path):
    d = _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.GRACE_AFTER_TERMINAL = 999
    stub_gh_sequence(tmp_path / "bin", api_run_polls=[
        [_run(1, "beef", "completed", "success")],
        [_run(1, "beef", "completed", "success"), _run(2, "beef", "completed", "failure")]],
        runview=json.dumps({"jobs": []}))
    run_watcher_main(tmp_path, ["beef"])
    assert [json.loads(p.read_text())["run_id"] for p in d.glob("*.json")] == [2]


def test_main_stuck_run_does_not_starve(tmp_path):
    d = _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.GRACE_AFTER_TERMINAL = 0
    stub_gh(tmp_path / "bin", api_runs=[_run(1, "beef", "in_progress", None),
            _run(2, "beef", "completed", "failure")], runview=json.dumps({"jobs": []}))
    run_watcher_main(tmp_path, ["beef"])
    assert len(list(d.glob("*.json"))) == 1


def test_main_broad_watches_active_runs(tmp_path):  # safe-broad
    d = _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.GRACE_AFTER_TERMINAL = 0
    # HEAD sha 'zzz' has no run; broad discovery finds an active repo run that fails.
    stub_gh(tmp_path / "bin", api_runs=[_run(9, "other", "completed", "failure")],
            runview=json.dumps({"jobs": []}))
    run_watcher_main(tmp_path, ["zzz"], broad="1")
    assert len(list(d.glob("*.json"))) == 1


def test_main_all_green_writes_no_marker(tmp_path):
    d = _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.GRACE_AFTER_TERMINAL = 0
    stub_gh(tmp_path / "bin", api_runs=[_run(1, "beef", "completed", "success")])
    run_watcher_main(tmp_path, ["beef"])
    assert list(d.glob("*.json")) == []


def test_main_no_gh_exits_clean(tmp_path):
    _use_dirs(tmp_path)
    WATCHER.POLL_INTERVAL = 0
    WATCHER.WATCH_CAP = 0.2
    WATCHER.GRACE_AFTER_TERMINAL = 0
    empty = tmp_path / "e"
    empty.mkdir()
    os.environ["PATH"] = str(empty)
    run_watcher_main(tmp_path, ["beef"])   # returns (bounded), no raise


# --------------------------------------------------------------------------
# Task 4 (cont.): durable atomic marker (retry + fallback, returns bool)
# --------------------------------------------------------------------------

def test_write_marker_atomic_true(tmp_path):
    _use_dirs(tmp_path)
    assert WATCHER._write_marker({"id": 55, "head_sha": "b", "name": "CI", "conclusion": "failure"},
                                 "o/n", "main", ["pytest"]) is True
    d = WATCHER.FAILURES_DIR
    assert sorted(p.name for p in d.glob("*")) == ["55.json"]
    m = json.loads((d / "55.json").read_text())
    assert m["run_url"] == "https://github.com/o/n/actions/runs/55" and m["failed_jobs"] == ["pytest"]


def test_write_marker_falls_back_when_primary_unwritable(tmp_path):  # A-4
    _use_dirs(tmp_path)
    (tmp_path / "f").write_text("i am a file")          # primary dir path is a file -> mkdir fails
    assert WATCHER._write_marker({"id": 7, "conclusion": "failure"}, "o/n", "m", []) is True
    assert (WATCHER.FALLBACK_DIR / "7.json").exists()   # written to fallback, not lost


def test_write_marker_false_only_when_both_fail(tmp_path):
    _use_dirs(tmp_path)
    (tmp_path / "f").write_text("x")
    (tmp_path / "fb").write_text("x")   # both unwritable
    assert WATCHER._write_marker({"id": 1, "conclusion": "failure"}, "o/n", "m", []) is False


# --------------------------------------------------------------------------
# Task 5: inject scans both dirs, consume-after-output, bad-schema isolation
# --------------------------------------------------------------------------

def test_inject_scans_both_dirs_ordering_and_isolation(tmp_path, capsys):
    _use_dirs(tmp_path)
    INJECT.FAILURES_DIR.mkdir(parents=True)
    INJECT.FALLBACK_DIR.mkdir(parents=True)
    (INJECT.FAILURES_DIR / "1.json").write_text(json.dumps(
        {"repo": "o/n", "branch": "main", "run_url": "u", "failed_jobs": ["j"]}))
    (INJECT.FALLBACK_DIR / "2.json").write_text(json.dumps(
        {"repo": "o/n", "branch": "dev", "run_url": "v", "failed_jobs": []}))  # fallback surfaced too
    (INJECT.FAILURES_DIR / "3.json").write_text("{ corrupt")
    (INJECT.FAILURES_DIR / "4.json").write_text(json.dumps({"nope": 1}))       # bad schema
    INJECT.main()
    out = capsys.readouterr().out
    assert "o/n @ main" not in out  # (format uses different wording; assert the identifiers)
    assert "main" in out and "dev" in out                                       # both good surfaced
    assert "WARNING" in out and "3.json" in out and "4.json" in out             # both bad warned
    assert not (INJECT.FAILURES_DIR / "1.json").exists()
    assert not (INJECT.FALLBACK_DIR / "2.json").exists()
    assert (INJECT.FAILURES_DIR / "3.json").exists() and (INJECT.FAILURES_DIR / "4.json").exists()


def test_disable_escape_hatch(run_hook, make_event):
    os.environ["CT_CI_WATCH_DISABLE"] = "1"
    assert run_hook("ci-watch-arm.py", make_event("Bash", command="git push")).stdout.strip() == ""
    assert run_hook("ci-watch-inject.py", {"tool_name": "UserPromptSubmit"}).stdout.strip() == ""


# --------------------------------------------------------------------------
# Task 6: classifier via the shared tokenizer (glued separators + option values)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,expected", [
    ("git push", "push"), ("git -C /repo push", "push"), ("git --exec-path=/x push", "push"),
    ("gh pr create --fill", "pr-create"), ("gh pr merge 42 --squash", "pr-merge"),
    ("gh -R o/n pr merge 42", "pr-merge"),                # -R value before subcommand
    ("gh pr merge 42&&echo", "pr-merge"),                 # A-3 glued separator
    ("gh pr create&&git push", "pr-create"),
    ("git commit -m x", None), ("gh pr view 42", None), ("ls", None),
])
def test_classify_trigger(cmd, expected):
    assert ARM._classify_trigger(cmd) == expected


# --------------------------------------------------------------------------
# Task 7: push resolution (every source SHA, real remote, safe-broad fallback)
# --------------------------------------------------------------------------

def test_pushed_source_shas(tmp_path):
    repo, sha = divergent_repo(tmp_path)
    HEAD, MAIN, V1 = sha("HEAD"), sha("main"), sha("v1")
    assert HEAD != MAIN

    def f(c):
        return ARM._pushed_source_shas(str(repo), c)

    assert f("git push") == {HEAD}
    assert f("git push origin main") == {MAIN}
    assert f("git push --repo=origin main") == {MAIN}
    assert f("git push origin main feat/x") == {MAIN, HEAD}
    assert f("git push --tags") == {V1}
    assert f("git push --all") == {HEAD, MAIN}
    assert f("git push --mirror") == {HEAD, MAIN, V1}
    assert f("gh pr create --fill") == set()


def test_is_ambiguous_push(tmp_path):
    f = ARM._is_ambiguous_push
    assert f("git push origin main") is False and f("git push") is False
    assert f("git push --branches") is True
    assert f("git push origin 'refs/heads/*:refs/heads/*'") is True
    assert f("git push origin :") is True


def test_push_remote_nwo_non_origin(tmp_path):  # A-2
    repo, _ = init_repo(tmp_path, origin="git@github.com:client/api.git")
    subprocess.run(["git", "-C", str(repo), "remote", "add", "upstream",
                    "https://github.com/upstream-org/api.git"], check=True)

    def f(c):
        return ARM._push_remote_nwo(str(repo), c)

    assert f("git push") == "client/api"
    assert f("git push upstream main") == "upstream-org/api"
    assert f("git push git@github.com:other/repo.git main") == "other/repo"


def test_resolve_target_push_pr_create_and_ambiguous(tmp_path):
    repo, sha = divergent_repo(tmp_path)
    os.chdir(repo)
    stub_gh(tmp_path / "bin")   # no gh needed for push
    r1 = ARM._resolve_target("git push origin main feat/x", ARM.MODE_PUSH)
    assert r1 and r1[2] == {sha("main"), sha("HEAD")} and r1[5] == "0"   # (…, broad="0")
    r2 = ARM._resolve_target("gh pr create --fill", ARM.MODE_PUSH)       # R3-2 reachable
    assert r2 and r2[2] == {sha("HEAD")}
    r3 = ARM._resolve_target("git push --branches", ARM.MODE_PUSH)       # safe-broad
    assert r3 and r3[5] == "1" and sha("HEAD") in r3[2]                  # broad; HEAD anchored


# --------------------------------------------------------------------------
# Task 8: merge selector/SHA, cross-repo lock, repo override, arm contract
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,expected", [
    ("gh pr merge 42 --squash", "42"),
    ("gh pr merge https://github.com/o/n/pull/9", "https://github.com/o/n/pull/9"),
    ("gh pr merge my-branch", "my-branch"), ("gh pr merge --match-head-commit 1234567", None),
    ("gh -R o/n pr merge 42", "42"), ("gh pr merge 42&&echo", "42"),   # A-3 glued
])
def test_pr_selector(cmd, expected):
    assert ARM._pr_selector(cmd) == expected


@pytest.mark.parametrize("cmd,expected", [
    ("gh -R o/n pr merge 42", "o/n"), ("gh pr merge 42 -R other/repo", "other/repo"),
    ("gh pr merge 42", None),
])
def test_gh_repo_override(cmd, expected):
    assert ARM._gh_repo_override(cmd) == expected


def test_lock_name_includes_repo_identity(tmp_path):  # A-1
    shas = ",".join(sorted(["a" * 40, "b" * 40]))
    n1 = ARM._lock_name("client/api", "/work/client/api", shas)
    n2 = ARM._lock_name("fork/api", "/work/fork/api", shas)
    assert n1 != n2                                     # same SHA set, different repo -> distinct
    # and distinct sha-sets in one repo still differ:
    assert ARM._lock_name("o/n", "/r", "a" + ",b") != ARM._lock_name("o/n", "/r", "a" + ",c")


def test_resolve_target_merge(tmp_path):
    repo, _ = init_repo(tmp_path)
    os.chdir(repo)
    stub_gh(tmp_path / "bin", prview=json.dumps({"mergeCommit": {"oid": "a" * 40}, "baseRefName": "main"}))
    got = ARM._resolve_target("gh pr merge 42 -R other/repo --squash", ARM.MODE_MERGE)
    assert got and got[2] == {"a" * 40} and got[1] == "main" and got[4] == "other/repo" and got[5] == "0"


def test_resolve_target_merge_broad_when_no_commit(tmp_path):  # safe-broad, incl --auto
    repo, _ = init_repo(tmp_path)
    os.chdir(repo)
    stub_gh(tmp_path / "bin", prview=json.dumps({"mergeCommit": None}))
    got = ARM._resolve_target("gh pr merge 42 --auto", ARM.MODE_MERGE)
    assert got and got[5] == "1"                        # broad watch (sees nothing in-window -> exits)


# --------------------------------------------------------------------------
# Task 9: arm idempotency, cross-repo distinctness, spawn cleanup, stale sweep
# --------------------------------------------------------------------------

def _use_armed(tmp_path):
    ARM.CI_WATCH_DIR = tmp_path / "cw"
    ARM.ARMED_DIR = ARM.CI_WATCH_DIR / "armed"


def _stub_watcher(tmp_path):
    s = tmp_path / "sw.py"
    s.write_text("import sys; sys.exit(0)\n")
    ARM.WATCHER = s


def test_arm_idempotent(tmp_path):
    _use_armed(tmp_path)
    _stub_watcher(tmp_path)
    a = ARM._arm(str(tmp_path), "x", {"c" * 40}, "t", "o/n", "0", ARM.MODE_PUSH)
    b = ARM._arm(str(tmp_path), "x", {"c" * 40}, "t", "o/n", "0", ARM.MODE_PUSH)
    assert a is True and b is False and len(list(ARM.ARMED_DIR.glob("*.lock"))) == 1


def test_arm_cross_repo_no_collision(tmp_path):  # A-1 end-to-end
    # Real existing repo roots (arm spawns the watcher with cwd=repo_root): two
    # DIFFERENT repos with the SAME SHA set must produce two DISTINCT locks.
    _use_armed(tmp_path)
    _stub_watcher(tmp_path)
    shas = {"a" * 40, "b" * 40}
    client = tmp_path / "client_api"
    client.mkdir()
    fork = tmp_path / "fork_api"
    fork.mkdir()
    assert ARM._arm(str(client), "x", shas, "t", "client/api", "0", ARM.MODE_PUSH) is True
    assert ARM._arm(str(fork), "x", shas, "t", "fork/api", "0", ARM.MODE_PUSH) is True
    assert len(list(ARM.ARMED_DIR.glob("*.lock"))) == 2


def test_arm_unlinks_lock_on_spawn_failure(tmp_path):
    _use_armed(tmp_path)
    s = tmp_path / "sw.py"
    s.write_text("pass\n")
    ARM.WATCHER = s
    assert ARM._arm("/no/such/repo", "x", {"d" * 40}, "t", "o/n", "0", ARM.MODE_PUSH) is False
    assert list(ARM.ARMED_DIR.glob("*.lock")) == []


def test_sweep_removes_only_stale_locks(tmp_path):
    _use_armed(tmp_path)
    ARM.ARMED_DIR.mkdir(parents=True)
    (ARM.ARMED_DIR / "fresh.lock").write_text("{}")
    stale = ARM.ARMED_DIR / "stale.lock"
    stale.write_text("{}")
    old = time.time() - (ARM.STALE_LOCK_SECS + 60)
    os.utime(stale, (old, old))
    ARM._sweep_stale_locks()
    assert {p.name for p in ARM.ARMED_DIR.glob("*.lock")} == {"fresh.lock"}


# --------------------------------------------------------------------------
# Task 10: dispatcher wiring (runtime module config, not source text)
# --------------------------------------------------------------------------

def test_posttooluse_bash_chain_includes_ci_watch_arm():
    assert Path(POD.CI_WATCH_ARM).name == "ci-watch-arm.py"
    assert POD.CI_WATCH_ARM in POD.BASH_HANDLERS
    # arm runs after the loop/lint handlers (side-effect-only, emits no decision).
    assert POD.BASH_HANDLERS[-1] == POD.CI_WATCH_ARM


def test_prompt_dispatcher_wires_inject_last_and_guard_first():
    assert Path(PD.HOOK_PATHS[0]).name == "paul-apply-review-guard.py"   # Path A fence stays first
    assert Path(PD.HOOK_PATHS[-1]).name == "ci-watch-inject.py"           # inject appended last
    # no duplicate registration:
    assert [p for p in PD.HOOK_PATHS if Path(p).name == "ci-watch-inject.py"] == [PD.HOOK_PATHS[-1]]


def test_posttooluse_missing_handler_does_not_block(run_hook, make_event):
    # A registered Bash handler that is not on disk (ci-watch-arm.py is not deployed
    # to ~/.claude/hooks in this checkout) must NOT be misread as an exit-2 block:
    # `python3 <missing>` exits 2, which the dispatcher now skips rather than
    # propagating. An innocuous Bash PostToolUse therefore exits 0, never 2.
    result = run_hook("posttooluse-dispatcher.py", make_event("Bash", command="git status"))
    assert result.returncode == 0
