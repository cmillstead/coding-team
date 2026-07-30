import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/


class TestCiOrphanDetectorSyntax:
    def test_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


class TestCiOrphanDetectorBehavior:
    def test_exits_cleanly_with_empty_input(self):
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            input="", capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0

    def test_exits_cleanly_when_gh_not_available(self):
        # Provide a PATH that includes bash but NOT gh
        result = subprocess.run(
            ["bash", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            input="", capture_output=True, text=True, timeout=15,
            env={"PATH": "/bin:/usr/bin"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


class TestStaleBranchDetection:
    def test_stale_branch_section_exists(self):
        """Verify the script contains stale branch detection code."""
        script = (HOOKS_DIR / "ci-orphan-detector.sh").read_text()
        assert "Stale branch detection" in script
        assert "stale_lines" in script
        assert "cutoff" in script
        assert "git branch" in script
        # Verify the bash syntax is still valid after adding stale branch code
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_script_syntax_valid(self):
        """Run bash -n to verify no syntax errors in the complete script."""
        result = subprocess.run(
            ["bash", "-n", str(HOOKS_DIR / "ci-orphan-detector.sh")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"
        assert result.stderr.strip() == "", f"Unexpected warnings: {result.stderr}"


# ---------------------------------------------------------------------------
# Fixture machinery for the parked-merged-branch detection tests below.
# ---------------------------------------------------------------------------

_GIT_IDENTITY = ["-c", "user.email=t@t", "-c", "user.name=t"]
_OLD_DATE = "2020-01-01T00:00:00"


def _run(args, cwd=None, env=None, check=True):
    return subprocess.run(
        args, cwd=str(cwd) if cwd is not None else None, env=env,
        check=check, capture_output=True, text=True,
    )


def make_repo(path: Path, branch: str = "main", old: bool = False) -> Path:
    """git init -b main; one identity-stamped commit; optional checkout -b <branch>.

    old=True stamps the (single) commit with GIT_AUTHOR_DATE/GIT_COMMITTER_DATE
    far in the past, for stale-branch scenarios.
    """
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-b", "main"], cwd=path)
    commit_env = os.environ.copy()
    if old:
        commit_env["GIT_AUTHOR_DATE"] = _OLD_DATE
        commit_env["GIT_COMMITTER_DATE"] = _OLD_DATE
    _run(
        ["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "x"],
        cwd=path, env=commit_env,
    )
    if branch != "main":
        _run(["git", "checkout", "-b", branch], cwd=path)
    return path


def _head_sha(repo: Path) -> str:
    return _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()


def _commit_ts(repo: Path, ref: str) -> int:
    return int(_run(["git", "log", "-1", "--format=%ct", ref], cwd=repo).stdout.strip())


def _echo_json(obj) -> str:
    """A bash `echo '<json>'` line that safely emits obj as JSON."""
    return "echo " + shlex.quote(json.dumps(obj))


def gh_script(merged: str = "echo '[]'", orphan: str = "echo '[]'",
              open_heads: str = "echo '[]'") -> str:
    """Build the body of the fake `gh` shim: dispatches on the invocation shape."""
    return (
        'case "$*" in\n'
        '    *"--state merged"*)\n'
        f"        {merged}\n"
        "        ;;\n"
        '    *"statusCheckRollup"*)\n'
        f"        {orphan}\n"
        "        ;;\n"
        '    *"headRefName"*)\n'
        f"        {open_heads}\n"
        "        ;;\n"
        "    *)\n"
        "        echo '[]'\n"
        "        ;;\n"
        "esac\n"
    )


def make_shims(tmp_path: Path, gh_body: str):
    """Prepend a shim dir (fake gh + timeout passthrough) to the real PATH.

    Real jq/git/bash keep resolving through the inherited PATH. The gh shim
    logs every invocation's argv (one line per call) to <tmp>/gh-calls.log
    before dispatching via gh_body. The timeout shim passes through to the
    real command, stripping the leading `timeout`-style args (either the
    existing bare `<seconds>` form or the new `-k 1 2` form).
    """
    shim_dir = tmp_path / "shim-bin"
    shim_dir.mkdir(exist_ok=True)
    log_file = tmp_path / "gh-calls.log"

    gh_path = shim_dir / "gh"
    gh_path.write_text(
        "#!/bin/bash\n"
        f'printf \'%s\\n\' "$*" >> "{log_file}"\n'
        f"{gh_body}"
    )
    gh_path.chmod(0o755)

    timeout_path = shim_dir / "timeout"
    timeout_path.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = "-k" ]; then\n'
        "    shift 3\n"
        "else\n"
        "    shift 1\n"
        "fi\n"
        'exec "$@"\n'
    )
    timeout_path.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
    return env, log_file


def run_hook(cwd: Path, env: dict):
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "ci-orphan-detector.sh")],
        cwd=str(cwd), env=env, input="",
        capture_output=True, text=True, timeout=15,
    )
    return result.returncode, result.stdout, result.stderr


def parse_envelope(stdout: str) -> str:
    """Assert stdout is exactly ONE JSON object with decision=='allow', return reason."""
    obj = json.loads(stdout)
    assert isinstance(obj, dict), f"expected a single JSON object, got {obj!r}"
    assert obj.get("decision") == "allow", obj
    reason = obj.get("reason")
    assert isinstance(reason, str), obj
    return reason


def _expected_orphan_reason(items) -> str:
    """items: list of (number, title, failing_count)."""
    lines = []
    for number, title, failing in items:
        suffix = "s" if failing > 1 else ""
        lines.append(f"- #{number}: {title} ({failing} failing check{suffix})")
    orphan_lines = "\n".join(lines)
    return (
        "Open PRs with failing CI:\n"
        f"{orphan_lines}\n"
        "Address these first — fix CI failures or close with a reason. "
        "Starting new work while old PRs rot creates orphan debt."
    )


def _expected_stale_reason(branch_ages) -> str:
    """branch_ages: list of (branch_name, age_days)."""
    stale_lines = "".join(f"- {name} ({age}d old, no PR)\n" for name, age in branch_ages)
    return (
        "Stale local branches (>14d, no PR):\n"
        f"{stale_lines}\n"
        "Consider deleting with: git branch -d <name>"
    )


def _sh_single_quote(s: str) -> str:
    """Mirror the script's single-quote-safe escaping (sed "s/'/'\\\\''/g")
    for embedding a path/branch in the advertised recovery command."""
    return "'" + s.replace("'", "'\\''") + "'"


def _expected_parked_reason(entries) -> str:
    """entries: list of (label, branch, pr_number, abs_path, base)."""
    lines = [
        f"- {label}: '{branch}' — PR #{pr_number} merged. "
        f"Return: git -C {_sh_single_quote(abs_path)} checkout {_sh_single_quote(base)} "
        f"&& git -C {_sh_single_quote(abs_path)} pull --ff-only"
        for label, branch, pr_number, abs_path, base in entries
    ]
    return "Checkout parked on a MERGED branch:\n" + "\n".join(lines)


class TestParkedMergedBranchDetection:
    def test_parked_repo_warns(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        sha = _head_sha(repo)
        env, log_file = make_shims(
            tmp_path, gh_script(merged=_echo_json([{"number": 7, "headRefOid": sha}]))
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [(".", "feat/x", 7, str(repo.resolve()), "main")]
        )
        assert reason == expected

    def test_on_main_silent(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="main")
        env, log_file = make_shims(tmp_path, gh_script())
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""
        log_content = log_file.read_text() if log_file.exists() else ""
        assert "--state merged" not in log_content

    def test_on_master_silent(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="main")
        _run(["git", "branch", "-m", "master"], cwd=repo)
        env, log_file = make_shims(tmp_path, gh_script())
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""
        log_content = log_file.read_text() if log_file.exists() else ""
        assert "--state merged" not in log_content

    def test_detached_head_silent(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        _run(["git", "checkout", "--detach"], cwd=repo)
        env, log_file = make_shims(tmp_path, gh_script())
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""
        log_content = log_file.read_text() if log_file.exists() else ""
        assert "--state merged" not in log_content

    def test_gh_merged_query_fails_silent(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        env, log_file = make_shims(tmp_path, gh_script(merged="exit 1"))
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""

    def test_no_merged_pr_silent(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        env, log_file = make_shims(tmp_path, gh_script(merged="echo '[]'"))
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""

    def test_lookup_cap(self, tmp_path):
        root = make_repo(tmp_path / "root", branch="main")
        sub_names = []
        for i in range(3):
            make_repo(root / f"sub{i}", branch=f"feat/sub{i}")
            sub_names.append(f"sub{i}")
        gitmodules = "".join(
            f'[submodule "{name}"]\n    path = {name}\n    url = ../{name}\n'
            for name in sub_names
        )
        (root / ".gitmodules").write_text(gitmodules)
        env, log_file = make_shims(tmp_path, gh_script(merged="echo '[]'"))
        rc, out, err = run_hook(root, env)
        assert rc == 0
        assert err == ""
        log_content = log_file.read_text() if log_file.exists() else ""
        merged_calls = [l for l in log_content.splitlines() if "--state merged" in l]
        assert len(merged_calls) == 2

    def test_subdir_cwd_finds_root(self, tmp_path):
        root = make_repo(tmp_path / "root", branch="main")
        make_repo(root / "sub", branch="feat/sub")
        sub_sha = _head_sha(root / "sub")
        (root / ".gitmodules").write_text(
            '[submodule "sub"]\n    path = sub\n    url = ../sub\n'
        )
        (root / "src").mkdir()
        env, log_file = make_shims(
            tmp_path, gh_script(merged=_echo_json([{"number": 9, "headRefOid": sub_sha}]))
        )
        rc, out, err = run_hook(root / "src", env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [("sub", "feat/sub", 9, str((root / "sub").resolve()), "main")]
        )
        assert reason == expected

    def test_stale_oid_silent(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        env, log_file = make_shims(
            tmp_path,
            gh_script(merged=_echo_json(
                [{"number": 7, "headRefOid": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}]
            )),
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""

    def test_master_based_repo_parked_warns(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(["git", "init", "-b", "main"], cwd=repo)
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "x"], cwd=repo)
        _run(["git", "branch", "-m", "master"], cwd=repo)
        _run(["git", "checkout", "-b", "feat/x"], cwd=repo)
        sha = _head_sha(repo)
        env, log_file = make_shims(
            tmp_path, gh_script(merged=_echo_json([{"number": 11, "headRefOid": sha}]))
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [(".", "feat/x", 11, str(repo.resolve()), "master")]
        )
        assert reason == expected

    def test_no_timeout_no_lookup(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        sha = _head_sha(repo)

        bin_dir = tmp_path / "no-timeout-bin"
        bin_dir.mkdir()
        for tool in ("git", "jq", "bash"):
            real = shutil.which(tool)
            assert real is not None, f"{tool} not found via shutil.which"
            (bin_dir / tool).symlink_to(real)

        log_file = tmp_path / "gh-calls.log"
        gh_path = bin_dir / "gh"
        gh_path.write_text(
            "#!/bin/bash\n"
            f'printf \'%s\\n\' "$*" >> "{log_file}"\n'
            + gh_script(merged=_echo_json([{"number": 7, "headRefOid": sha}]))
        )
        gh_path.chmod(0o755)

        env = {"PATH": str(bin_dir)}
        if "HOME" in os.environ:
            env["HOME"] = os.environ["HOME"]

        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        log_content = log_file.read_text() if log_file.exists() else ""
        assert "--state merged" not in log_content
        assert out.strip() == ""


class TestCombinedOutputAssembly:
    def test_parked_only(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        sha = _head_sha(repo)
        env, log_file = make_shims(
            tmp_path, gh_script(merged=_echo_json([{"number": 7, "headRefOid": sha}]))
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [(".", "feat/x", 7, str(repo.resolve()), "main")]
        )
        assert reason == expected

    def test_stale_plus_parked(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(["git", "init", "-b", "main"], cwd=repo)
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "x"], cwd=repo)
        _run(["git", "checkout", "-b", "old-stale"], cwd=repo)
        old_env = os.environ.copy()
        old_env["GIT_AUTHOR_DATE"] = _OLD_DATE
        old_env["GIT_COMMITTER_DATE"] = _OLD_DATE
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "old"],
             cwd=repo, env=old_env)
        last_commit_ts = _commit_ts(repo, "old-stale")
        _run(["git", "checkout", "main"], cwd=repo)
        _run(["git", "checkout", "-b", "feat/parked"], cwd=repo)
        sha = _head_sha(repo)

        env, log_file = make_shims(
            tmp_path,
            gh_script(
                merged=_echo_json([{"number": 7, "headRefOid": sha}]),
                open_heads="echo '[]'",
            ),
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)

        age_days = (int(time.time()) - last_commit_ts) // 86400
        expected_stale = _expected_stale_reason([("old-stale", age_days)])
        expected_parked = _expected_parked_reason(
            [(".", "feat/parked", 7, str(repo.resolve()), "main")]
        )
        expected = expected_stale + "\n\n" + expected_parked
        assert reason == expected

    def test_orphan_plus_parked(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="feat/parked")
        sha = _head_sha(repo)
        orphan_body = _echo_json([
            {"number": 42, "title": "Broken thing",
             "statusCheckRollup": [{"conclusion": "FAILURE"}]}
        ])
        env, log_file = make_shims(
            tmp_path,
            gh_script(
                merged=_echo_json([{"number": 7, "headRefOid": sha}]),
                orphan=orphan_body,
                open_heads="echo '[]'",
            ),
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)

        expected_orphan = _expected_orphan_reason([(42, "Broken thing", 1)])
        expected_parked = _expected_parked_reason(
            [(".", "feat/parked", 7, str(repo.resolve()), "main")]
        )
        expected = expected_orphan + "\n\n" + expected_parked
        assert reason == expected

    def test_stale_only_output_unchanged(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(["git", "init", "-b", "main"], cwd=repo)
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "x"], cwd=repo)
        _run(["git", "checkout", "-b", "old-stale"], cwd=repo)
        old_env = os.environ.copy()
        old_env["GIT_AUTHOR_DATE"] = _OLD_DATE
        old_env["GIT_COMMITTER_DATE"] = _OLD_DATE
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "old"],
             cwd=repo, env=old_env)
        last_commit_ts = _commit_ts(repo, "old-stale")
        _run(["git", "checkout", "main"], cwd=repo)  # current branch = main -> no parked lookup

        env, log_file = make_shims(tmp_path, gh_script(open_heads="echo '[]'"))
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)

        age_days = (int(time.time()) - last_commit_ts) // 86400
        expected = _expected_stale_reason([("old-stale", age_days)])
        assert reason == expected

    def test_orphan_only_output_unchanged(self, tmp_path):
        repo = make_repo(tmp_path / "repo", branch="main")
        orphan_body = _echo_json([
            {"number": 5, "title": "Fix CI",
             "statusCheckRollup": [{"conclusion": "FAILURE"}, {"conclusion": "FAILURE"}]}
        ])
        env, log_file = make_shims(
            tmp_path, gh_script(orphan=orphan_body, open_heads="echo '[]'")
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_orphan_reason([(5, "Fix CI", 2)])
        assert reason == expected

    def test_orphan_plus_stale_output_unchanged(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _run(["git", "init", "-b", "main"], cwd=repo)
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "x"], cwd=repo)
        _run(["git", "checkout", "-b", "old-stale"], cwd=repo)
        old_env = os.environ.copy()
        old_env["GIT_AUTHOR_DATE"] = _OLD_DATE
        old_env["GIT_COMMITTER_DATE"] = _OLD_DATE
        _run(["git", *_GIT_IDENTITY, "commit", "--allow-empty", "-m", "old"],
             cwd=repo, env=old_env)
        last_commit_ts = _commit_ts(repo, "old-stale")
        _run(["git", "checkout", "main"], cwd=repo)

        orphan_body = _echo_json([
            {"number": 5, "title": "Fix CI", "statusCheckRollup": [{"conclusion": "FAILURE"}]}
        ])
        env, log_file = make_shims(
            tmp_path, gh_script(orphan=orphan_body, open_heads="echo '[]'")
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)

        age_days = (int(time.time()) - last_commit_ts) // 86400
        expected_orphan = _expected_orphan_reason([(5, "Fix CI", 1)])
        expected_stale = _expected_stale_reason([("old-stale", age_days)])
        expected = expected_orphan + "\n\n" + expected_stale
        assert reason == expected


class TestParkedMergedBranchQAFindings:
    """Regression coverage from the QA review round (7 findings)."""

    def test_submodule_path_with_space_detected(self, tmp_path):
        """Finding 1: a submodule path containing a space must not be
        truncated by naive whitespace-field parsing of `git config
        --get-regexp` output."""
        root = make_repo(tmp_path / "root", branch="main")
        sub_dir = root / "vendor" / "my lib"
        make_repo(sub_dir, branch="feat/space")
        sub_sha = _head_sha(sub_dir)
        (root / ".gitmodules").write_text(
            '[submodule "mylib"]\n    path = vendor/my lib\n    url = ../vendor/my-lib\n'
        )
        env, log_file = make_shims(
            tmp_path, gh_script(merged=_echo_json([{"number": 55, "headRefOid": sub_sha}]))
        )
        rc, out, err = run_hook(root, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [("vendor/my lib", "feat/space", 55, str(sub_dir.resolve()), "main")]
        )
        assert reason == expected

    def test_origin_head_base_used_over_local_main(self, tmp_path):
        """Finding 2: when origin/HEAD resolves to a branch OTHER than the
        local main/master fallback, the origin/HEAD branch must win."""
        repo = make_repo(tmp_path / "repo", branch="feat/y")
        # main exists locally (created by make_repo before the checkout -b),
        # but origin/HEAD points at "develop" — that must be the recovery base.
        _run(["git", "remote", "add", "origin", "/nonexistent/origin.git"], cwd=repo)
        _run(["git", "update-ref", "refs/remotes/origin/develop", "HEAD"], cwd=repo)
        _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD",
              "refs/remotes/origin/develop"], cwd=repo)
        sha = _head_sha(repo)
        env, log_file = make_shims(
            tmp_path, gh_script(merged=_echo_json([{"number": 21, "headRefOid": sha}]))
        )
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [(".", "feat/y", 21, str(repo.resolve()), "develop")]
        )
        assert reason == expected

    def test_merged_query_multiple_entries_finds_match(self, tmp_path):
        """Finding 3: an OLDER merged PR entry that does not match HEAD must
        not shadow a LATER entry that does (reused branch name, merged
        twice) — the query must scan all returned entries, not just [0]."""
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        sha = _head_sha(repo)
        merged_body = _echo_json([
            {"number": 5, "headRefOid": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"},
            {"number": 21, "headRefOid": sha},
        ])
        env, log_file = make_shims(tmp_path, gh_script(merged=merged_body))
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason(
            [(".", "feat/x", 21, str(repo.resolve()), "main")]
        )
        assert reason == expected

    def test_uninitialized_submodule_skipped(self, tmp_path):
        """Finding 4: a .gitmodules entry whose directory has no git
        checkout (never `git submodule update --init`) must be silently
        skipped, not error."""
        root = make_repo(tmp_path / "root", branch="main")
        (root / "empty-sub").mkdir()  # no git init here — uninitialized
        (root / ".gitmodules").write_text(
            '[submodule "empty-sub"]\n    path = empty-sub\n    url = ../empty-sub\n'
        )
        env, log_file = make_shims(tmp_path, gh_script())
        rc, out, err = run_hook(root, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""
        log_content = log_file.read_text() if log_file.exists() else ""
        assert "--state merged" not in log_content

    def test_two_parked_repos_joined(self, tmp_path):
        """Finding 5: two simultaneously parked repos (root + submodule) in
        one run must be joined as a single paragraph, one bullet per repo,
        newline-separated (not blank-line-separated)."""
        root = make_repo(tmp_path / "root", branch="feat/root")
        make_repo(root / "sub", branch="feat/sub")
        root_sha = _head_sha(root)
        sub_sha = _head_sha(root / "sub")
        (root / ".gitmodules").write_text(
            '[submodule "sub"]\n    path = sub\n    url = ../sub\n'
        )
        merged_case = (
            'case "$*" in\n'
            '    *"--head feat/root"*)\n'
            f"        {_echo_json([{'number': 31, 'headRefOid': root_sha}])}\n"
            "        ;;\n"
            '    *"--head feat/sub"*)\n'
            f"        {_echo_json([{'number': 32, 'headRefOid': sub_sha}])}\n"
            "        ;;\n"
            "    *)\n"
            "        echo '[]'\n"
            "        ;;\n"
            "esac\n"
        )
        env, log_file = make_shims(tmp_path, merged_case)
        rc, out, err = run_hook(root, env)
        assert rc == 0
        assert err == ""
        reason = parse_envelope(out)
        expected = _expected_parked_reason([
            (".", "feat/root", 31, str(root.resolve()), "main"),
            ("sub", "feat/sub", 32, str((root / "sub").resolve()), "main"),
        ])
        assert reason == expected

    def test_merged_query_non_json_silent(self, tmp_path):
        """Finding 6: gh exits 0 but prints non-JSON on stdout — silent skip."""
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        env, log_file = make_shims(tmp_path, gh_script(merged="echo 'not json'"))
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""

    def test_merged_pr_missing_head_ref_oid_silent(self, tmp_path):
        """Finding 7: a merged PR object entirely missing the headRefOid key
        must be silently skipped, not crash the comparison."""
        repo = make_repo(tmp_path / "repo", branch="feat/x")
        merged_body = _echo_json([{"number": 7}])  # no headRefOid key at all
        env, log_file = make_shims(tmp_path, gh_script(merged=merged_body))
        rc, out, err = run_hook(repo, env)
        assert rc == 0
        assert err == ""
        assert out.strip() == ""
