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
WATCHER_PATH = HOOKS_DIR / "ci-watcher.py"

_SNAPSHOT = {
    ARM: ("CI_WATCH_DIR", "ARMED_DIR", "WATCHER", "STALE_LOCK_SECS"),
    WATCHER: ("CI_WATCH_DIR", "FAILURES_DIR", "FALLBACK_DIR", "POLL_INTERVAL",
              "WATCH_CAP", "GRACE_AFTER_TERMINAL"),
    INJECT: ("FAILURES_DIR", "FALLBACK_DIR"),
}


@pytest.fixture(autouse=True)
def _restore_state():
    env = dict(os.environ); cwd = os.getcwd()
    saved = {(m, n): getattr(m, n, None) for m, names in _SNAPSHOT.items() for n in names}
    try:
        yield
    finally:
        os.environ.clear(); os.environ.update(env); os.chdir(cwd)
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


def init_repo(tmp_path, *, origin="git@github.com:o/n.git"):
    r = tmp_path / "repo"; r.mkdir()
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
    sha = lambda ref: subprocess.run(["git", "-C", str(repo), "rev-parse", ref],
                                     capture_output=True, text=True).stdout.strip()
    return repo, sha


def run_watcher_main(tmp_path, shas, *, nwo="o/n", armed_at="2000-01-01T00:00:00Z",
                     branch="feat/x", broad="0"):
    lock = tmp_path / "x.lock"; lock.write_text("{}")
    argv = [str(WATCHER_PATH), str(tmp_path), branch, ",".join(shas), str(lock), nwo, armed_at, broad]
    old = sys.argv; sys.argv = argv
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
