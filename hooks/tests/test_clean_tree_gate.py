"""Tests for clean-tree-gate.py hook — the plan-completion clean-tree guard.

Each test builds a fresh real git repo (no mocks) and runs the hook via
subprocess with a JSON event on stdin, mirroring production invocation.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent  # tests/ -> hooks/
HOOK_PATH = HOOKS_DIR / "clean-tree-gate.py"


def _load_guard():
    """Load clean-tree-gate.py as a module (hyphen in name requires importlib).

    Called INSIDE a test (not at import time) so that in the RED phase — before
    the guard file exists — only the one test that needs the in-process module
    fails (FileNotFoundError), instead of a whole-module collection error.
    """
    spec = importlib.util.spec_from_file_location("clean_tree_gate", str(HOOK_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t.t"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True, capture_output=True)


def _commit_all(root: Path, msg: str = "base") -> None:
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", msg], check=True, capture_output=True)


def _porcelain(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout


def _porcelain_z(root: Path) -> str:
    """`git status --porcelain -z --untracked-files=all` — the exact form the guard uses."""
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "-z", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout


def test_porcelain_primitive_shape(tmp_path):
    """Spike: assert the `-z --untracked-files=all` shape the guard depends on —
    untracked files listed INDIVIDUALLY (not a collapsed '?? sub/' dir), a
    rename record as two NUL fields (dest first, then source), gitignored files
    hidden, and NUL-terminated unquoted paths."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".gitignore").write_text("ignored.txt\n")
    (repo / "tracked.txt").write_text("v1\n")
    _commit_all(repo)
    # untracked file nested under a dir with NOTHING committed in it
    (repo / "sub").mkdir()
    (repo / "sub" / "new.txt").write_text("x\n")
    # staged rename of a committed file
    subprocess.run(["git", "-C", str(repo), "mv", "tracked.txt", "renamed.txt"],
                   check=True, capture_output=True)
    # gitignored dirty
    (repo / "ignored.txt").write_text("junk\n")
    fields = [f for f in _porcelain_z(repo).split("\0") if f]
    # -uall lists the untracked file individually, NOT a collapsed 'sub/' dir
    assert any(f.startswith("??") and f.endswith("sub/new.txt") for f in fields)
    assert not any(f.rstrip() == "?? sub/" for f in fields)
    # rename record: an 'R' entry (dest) with its source as the NEXT NUL field
    r_idx = next(i for i, f in enumerate(fields) if f.startswith("R"))
    assert fields[r_idx].endswith("renamed.txt")   # dest first in -z form
    assert fields[r_idx + 1] == "tracked.txt"       # source is a separate NUL field
    # gitignored file never listed
    assert not any("ignored.txt" in f for f in fields)


def _run(event: dict, cwd: Path, env: "dict | None" = None) -> tuple[str, int]:
    """Run the guard with `event` on stdin, from `cwd`. Return (stdout, returncode).

    `env`, if given, is layered OVER the current process env for the subprocess
    (used to inject a poisoned GIT_DIR/GIT_WORK_TREE for the FIX 8 test)."""
    run_env = {**os.environ, **env} if env else None
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(event), capture_output=True, text=True, timeout=10,
        cwd=str(cwd), env=run_env,
    )
    return result.stdout, result.returncode


def _edit_to_complete(plan: Path) -> dict:
    """Edit event flipping status: in-progress -> complete on `plan`."""
    return {"tool_name": "Edit", "tool_input": {
        "file_path": str(plan),
        "old_string": "status: in-progress",
        "new_string": "status: complete",
    }}


def _make_plan(repo: Path, status: str = "in-progress", extra: str = "") -> Path:
    plans = repo / "docs" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / "2026-09-02-feature.md"
    plan.write_text(f"---\nstatus: {status}\n---\n\n# Plan\n{extra}")
    return plan


def _edit_planned_to_in_progress(plan: Path) -> dict:
    """Edit event flipping status: planned -> in-progress on `plan`."""
    return {"tool_name": "Edit", "tool_input": {
        "file_path": str(plan),
        "old_string": "status: planned",
        "new_string": "status: in-progress",
    }}


def _tmpdir_env(tmp_path: Path) -> dict:
    """Isolate the baseline sidecar via a per-test TMPDIR (Finding 3 removed the
    bypass-capable CLEAN_TREE_BASELINE_FILE override). The hook subprocess
    computes the sidecar under tempfile.gettempdir(), which honors TMPDIR, so
    each test's sidecar lives in its own dir. Layer the returned env over the
    process env in _run/_arm; locate the sidecar with _the_sidecar(env)."""
    d = tmp_path / "tmp"
    d.mkdir(exist_ok=True)
    return {"TMPDIR": str(d)}


def _the_sidecar(env: dict) -> Path:
    """The single baseline sidecar written under this test's TMPDIR."""
    files = list(Path(env["TMPDIR"]).glob("coding-team-clean-tree-baseline-*.json"))
    assert len(files) == 1, f"expected exactly one sidecar, got {files}"
    return files[0]


def _arm(plan: Path, cwd: Path, env: dict) -> None:
    """Faithfully simulate arming: run the hook with the planned -> in-progress
    event (assert ALLOW so the snapshot is captured), THEN apply the flip to
    disk the real Edit tool would have made — completion detection reads PRE
    status from disk, so the file must actually say `in-progress` afterward.
    `env` MUST be a _tmpdir_env(...) so the snapshot lands in the test's TMPDIR.

    P3/FIX 4 (Codex): also assert PRODUCTION `_read_baseline` ACCEPTS the sidecar
    (returns non-None), so an allow-oriented test that relies on `_arm` genuinely
    exercises baseline SUBTRACTION at completion, not the missing/corrupt-baseline
    fail-open branch (a fail-open would ALLOW even without a real snapshot, hiding
    a broken subtraction). Uses the production reader — not a hand-rolled schema
    check — so it can never drift from (or repeat a bug of) the real validation.
    The sidecar lives under the subprocess's TMPDIR, so redirect the in-process
    `tempfile.gettempdir()` there and feed the reader the plan_root/plan_rel the
    hook stored (which reproduce the same hashed filename)."""
    out, rc = _run(_edit_planned_to_in_progress(plan), cwd=cwd, env=env)
    _assert_allow(out, rc)
    plan.write_text(plan.read_text().replace("status: planned", "status: in-progress", 1))
    stored = json.loads(_the_sidecar(env).read_text())
    guard = _load_guard()
    orig_tempdir = tempfile.tempdir
    tempfile.tempdir = env["TMPDIR"]   # so _baseline_file_path resolves under TMPDIR
    try:
        parsed = guard._read_baseline(Path(stored["plan_root"]), stored["plan_rel"])
    finally:
        tempfile.tempdir = orig_tempdir
    assert parsed is not None, (
        "production _read_baseline REJECTED the arming sidecar — allow-tests would "
        "pass via fail-open, not real subtraction"
    )


def _assert_block(stdout: str):
    assert '"decision": "block"' in stdout, f"expected BLOCK, got: {stdout!r}"


def _assert_allow(stdout: str, rc: int):
    # FIX 4: assert BOTH exit 0 AND empty stdout. In the RED phase the guard
    # file is absent, so the subprocess prints its error to STDERR and exits
    # non-zero — stdout is empty but rc != 0. Asserting only empty stdout would
    # make every ALLOW test PASS with NO guard (a false RED); the rc==0 check
    # makes a missing/crashing guard correctly FAIL the ALLOW tests.
    assert rc == 0 and stdout.strip() == "", (
        f"expected ALLOW (exit 0, no output), got rc={rc}, stdout={stdout!r}"
    )


def test_transition_with_modified_tracked_file_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                    # baseline empty (tree clean)
    (repo / "src.py").write_text("v2\n")     # NEW modification since baseline
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_transition_with_untracked_file_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    (repo / "new.txt").write_text("x\n")     # NEW untracked since baseline
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_transition_clean_tree_allows_and_excludes_plan(tmp_path):
    """D1: only the plan file is dirty -> excluded -> ALLOW. Arm-first so the
    allow is 'no new dirt', not fail-open.

    NOTE: a plan file showing up in porcelain is REAL for this tmp test repo
    (which tracks docs/plans), and for any downstream coding-team PROJECT that
    tracks docs/plans. It does NOT happen in coding-team's OWN repo, where
    docs/plans is gitignored. So the plan-file exclusion is load-bearing for
    those downstream projects — it is not dead code to 'simplify' away just
    because this harness never exercises it in production."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    plan.write_text(plan.read_text() + "- [x] tick\n")   # dirty ONLY the plan
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_transition_only_gitignored_dirty_allows(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".gitignore").write_text("ignored.txt\n")
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    (repo / "ignored.txt").write_text("junk\n")   # dirty but gitignored (never in porcelain)
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_non_completion_edit_with_dirty_tree_allows(tmp_path):
    """Edit ticks a checkbox (status stays in-progress) -> not a transition -> ALLOW."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")   # dirty
    event = {"tool_name": "Edit", "tool_input": {
        "file_path": str(plan),
        "old_string": "# Plan",
        "new_string": "# Plan\n- [x] a task",  # does NOT touch status
    }}
    out, rc = _run(event, cwd=repo)
    _assert_allow(out, rc)


def test_non_plan_file_edit_with_dirty_tree_allows(tmp_path):
    # A documented NON-TRANSITION case: src.py has no `status: in-progress`
    # frontmatter, so _is_completion_transition returns False regardless of
    # location. This does NOT prove the _is_plan_file branch (it would pass even
    # if _is_plan_file were hardcoded True) — that branch is discriminated by
    # test_non_plan_file_with_real_transition_frontmatter_allows below. Kept only
    # to document that a dirty tree plus an ordinary source edit stays allowed.
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _make_plan(repo)
    src = repo / "src.py"
    src.write_text("v1\n")
    _commit_all(repo)
    src.write_text("v2\n")
    event = {"tool_name": "Edit", "tool_input": {
        "file_path": str(src),
        "old_string": "status: in-progress",   # even if content looks like a transition
        "new_string": "status: complete",
    }}
    out, rc = _run(event, cwd=repo)
    _assert_allow(out, rc)


def test_non_plan_file_with_real_transition_frontmatter_allows(tmp_path):
    """Discriminator for the _is_plan_file branch (which runs BEFORE the
    transition check in main()). The edited file is a NON-plan .md that
    genuinely carries `status: in-progress` on disk and is flipped to
    `status: complete` while the tree is dirty — a REAL completion transition
    in every respect EXCEPT its location (not under docs/plans/). Correct
    behavior: ALLOW. This BLOCKs if _is_plan_file ever regresses to always-True
    (real transition + dirty tree), and ALLOWs when correct — the
    discrimination the frontmatter-less test above lacks."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _make_plan(repo)  # a real in-progress plan exists, but we are NOT editing it
    notes = repo / "notes.md"
    notes.write_text("---\nstatus: in-progress\n---\n\n# Notes\n")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)                      # tree clean
    (repo / "src.py").write_text("v2\n")   # dirty, non-plan work
    event = {"tool_name": "Edit", "tool_input": {
        "file_path": str(notes),           # NOT under docs/plans/
        "old_string": "status: in-progress",
        "new_string": "status: complete",  # a genuine in-progress -> complete flip
    }}
    out, rc = _run(event, cwd=repo)
    _assert_allow(out, rc)


def test_write_tool_completion_transition_with_dirty_tree_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    (repo / "src.py").write_text("v2\n")     # NEW dirt
    event = {"tool_name": "Write", "tool_input": {
        "file_path": str(plan), "content": "---\nstatus: complete\n---\n\n# Plan\n"}}
    out, rc = _run(event, cwd=repo, env=env)
    _assert_block(out)


def test_replace_all_completion_transition_with_dirty_tree_blocks(tmp_path):
    """Decoy `note: in-progress` before the real `status:`. Plan starts with
    `note: in-progress` + `status: planned`; arm flips ONLY status (targeted);
    the completion Edit uses replace_all 'in-progress'->'complete' which must flip
    BOTH the decoy note and status. A single-replacement impl flips only the decoy
    -> status stays in-progress -> non-transition -> ALLOW (fails this BLOCK)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plans = repo / "docs" / "plans"
    plans.mkdir(parents=True)
    plan = plans / "feature.md"
    plan.write_text("---\nnote: in-progress\nstatus: planned\n---\n\n# Plan\n")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                    # flips status: planned -> in-progress only
    (repo / "src.py").write_text("v2\n")     # NEW dirt
    event = {"tool_name": "Edit", "tool_input": {
        "file_path": str(plan), "old_string": "in-progress",
        "new_string": "complete", "replace_all": True}}
    out, rc = _run(event, cwd=repo, env=env)
    _assert_block(out)


def test_transition_plan_only_untracked_in_docs_allows(tmp_path):
    """--untracked-files=all lists the untracked plan individually so it is
    excluded even when docs/ is otherwise untracked. Arm-first."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README").write_text("x\n")
    _commit_all(repo)                        # HEAD exists; docs/ fully untracked
    plan = _make_plan(repo, status="planned")   # docs/plans/...md, untracked
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                    # arms while planned+untracked
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_transition_plan_filename_with_space_allows(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plans = repo / "docs" / "plans"
    plans.mkdir(parents=True)
    plan = plans / "my plan.md"
    plan.write_text("---\nstatus: planned\n---\n\n# Plan\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    plan.write_text(plan.read_text() + "- [x] tick\n")   # dirty ONLY the plan
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_transition_with_uncommitted_rename_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    subprocess.run(["git", "-C", str(repo), "mv", "src.py", "other.py"],
                   check=True, capture_output=True)   # NEW uncommitted rename
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_transition_git_env_poisoned_still_blocks(tmp_path):
    """FIX 8 preserved: an ambient GIT_DIR/GIT_WORK_TREE at a CLEAN decoy must not
    redirect the completion `git status`. Arm with a clean env; complete with the
    poison layered on TOP of the baseline env — the scrub still sees the dirty
    target, so the NEW src.py dirt BLOCKs."""
    target = tmp_path / "target"
    target.mkdir()
    _init_repo(target)
    plan = _make_plan(target, status="planned")
    (target / "src.py").write_text("v1\n")
    _commit_all(target)
    env = _tmpdir_env(tmp_path)
    _arm(plan, target, env)
    (target / "src.py").write_text("v2\n")   # NEW dirt
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    _init_repo(decoy)
    (decoy / "keep.txt").write_text("x\n")
    _commit_all(decoy)   # decoy clean
    poisoned = {**env, "GIT_DIR": str(decoy / ".git"), "GIT_WORK_TREE": str(decoy)}
    out, rc = _run(_edit_to_complete(plan), cwd=target, env=poisoned)
    _assert_block(out)


def test_dirty_entries_keeps_rename_to_plan_dest(tmp_path):
    """FIX 11 invariant — a rename whose DEST equals plan_rel is real dirt (the
    source moved) and is NOT excluded by _dirty_entries_excluding_plan."""
    guard = _load_guard()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "src_plan.md").write_text("---\nstatus: in-progress\n---\n\n# Plan\n")
    _commit_all(repo)
    (repo / "docs" / "plans").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "mv", "src_plan.md",
                    "docs/plans/feature.md"], check=True, capture_output=True)
    entries = guard._dirty_entries_excluding_plan(repo, "docs/plans/feature.md")
    assert any(("R" in xy or "C" in xy) and path == "docs/plans/feature.md"
               for (xy, path, _src) in entries)


def test_parse_porcelain_z_multi_record_alignment():
    """Unit test for _parse_porcelain_z (FIX 11): a rename record (two NUL fields,
    dest first) FOLLOWED by an ordinary entry must parse to EXACTLY two entries
    with correct alignment — the rename must not swallow the following entry, and
    the trailing NUL must not produce a phantom entry. Loads the guard in-process
    (so in RED this ONE test fails with FileNotFoundError, not the whole module)."""
    guard = _load_guard()
    stream = b"R  docs/plans/feature.md\x00old_src.md\x00 M src.py\x00"
    assert guard._parse_porcelain_z(stream) == [
        ("R ", "docs/plans/feature.md", "old_src.md"),
        (" M", "src.py", ""),
    ]


def test_plan_file_not_in_any_repo_allows(tmp_path):
    """No owning git repo -> allow. Uses a dir OUTSIDE any repo (pytest basetemp
    is inside the coding-team repo, so tmp_path alone would resolve to it)."""
    outside = Path(tempfile.mkdtemp())
    # Precondition: this dir is genuinely not in a git repo (else the test is vacuous).
    probe = subprocess.run(["git", "-C", str(outside), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
    assert probe.returncode != 0, "test dir must not be inside a git repo"
    plans = outside / "docs" / "plans"
    plans.mkdir(parents=True)
    plan = plans / "2026-09-02-feature.md"
    plan.write_text("---\nstatus: in-progress\n---\n\n# Plan\n")
    out, rc = _run(_edit_to_complete(plan), cwd=outside)
    _assert_allow(out, rc)


DISPATCHER = HOOKS_DIR / "pretooluse-dispatcher.py"


def _run_dispatcher(event: dict, cwd: Path, env: dict) -> tuple[str, int]:
    run_env = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, str(DISPATCHER)], input=json.dumps(event),
        capture_output=True, text=True, timeout=10, cwd=str(cwd), env=run_env)
    return result.stdout, result.returncode


def test_dispatcher_routes_completion_transition_to_clean_tree_gate(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    out, rc = _run_dispatcher(_edit_planned_to_in_progress(plan), repo, env)   # arm via dispatcher
    # Arming must not BLOCK. A sibling advisory hook (engram reference-data) may
    # add non-blocking additionalContext on a plan-file edit, so assert the
    # absence of a block decision rather than empty stdout.
    assert rc == 0 and '"decision": "block"' not in out
    plan.write_text(plan.read_text().replace("status: planned", "status: in-progress", 1))
    (repo / "src.py").write_text("v2\n")           # NEW dirt
    out, rc = _run_dispatcher(_edit_to_complete(plan), repo, env)
    assert '"decision": "block"' in out


def test_dispatcher_allows_non_plan_edit(tmp_path):
    """A non-plan Edit passes through the dispatcher untouched (no output)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _make_plan(repo)
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")
    result = subprocess.run(
        [sys.executable, str(DISPATCHER)],
        input=json.dumps({"tool_name": "Edit", "tool_input": {
            "file_path": str(repo / "src.py"), "old_string": "v1", "new_string": "v2"}}),
        capture_output=True, text=True, timeout=10, cwd=str(repo),
    )
    assert result.stdout.strip() == "" and result.returncode == 0


def test_dispatcher_clean_tree_precedes_write_guard_advisory(tmp_path):
    """Ordering (FIX 7) preserved: clean-tree runs BEFORE write-guard, so a dirty
    completion whose plan content also triggers write-guard's C1 allow-advisory
    is still BLOCKED. Arm-first."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    out, rc = _run_dispatcher(_edit_planned_to_in_progress(plan), repo, env)
    assert rc == 0 and '"decision": "block"' not in out   # arming must not block
    plan.write_text(plan.read_text().replace("status: planned", "status: in-progress", 1))
    (repo / "src.py").write_text("v2\n")           # NEW dirt
    content = ("---\nstatus: complete\n---\n\n# Plan\n\n"
               "See docs/plans/feature.md and call path.resolve() here.\n")
    out, rc = _run_dispatcher(
        {"tool_name": "Write", "tool_input": {"file_path": str(plan), "content": content}},
        repo, env)
    assert '"decision": "block"' in out


def _add_worktree(main_root: Path, wt_path: Path, branch: str) -> None:
    """Create a linked worktree of `main_root` at `wt_path` on a new `branch`.

    A linked worktree has its OWN working tree but SHARES `.git` with the main
    checkout — so uncommitted work here is invisible to `git status` run in the
    main checkout, which is exactly the leak the all-worktrees scan closes.
    """
    subprocess.run(["git", "-C", str(main_root), "worktree", "add", "-b", branch,
                    str(wt_path)], check=True, capture_output=True)


def test_new_dirty_in_linked_worktree_after_baseline_blocks(tmp_path):
    """C1 (QA HIGH) — replaces test_transition_dirty_linked_worktree_blocks. A
    linked worktree CLEAN at arming; new uncommitted work appears in it after;
    completion on the MAIN plan must BLOCK naming the worktree."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feature")   # clean at arming
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                         # baseline: main + wt both empty
    (wt / "feature.py").write_text("v1\n")        # NEW worktree dirt
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_block(out)
    assert str(wt) in out or "wt" in out


def test_preexisting_dirty_in_linked_worktree_allows(tmp_path):
    """C2 — worktree junk that predates arming is subtracted like main junk."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feature")
    (wt / "pre.py").write_text("v1\n")            # dirty BEFORE arming
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                         # baseline includes wt/pre.py
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)   # untouched
    _assert_allow(out, rc)


def test_worktree_created_after_baseline_with_dirt_blocks(tmp_path):
    """C3 — a worktree that did not exist at arming has NO baseline entry, so all
    its dirt is new. Cannot be dodged by deferring worktree creation."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                         # baseline = main only, clean
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feature")   # created AFTER
    (wt / "feature.py").write_text("v1\n")        # uncommitted
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_block(out)


def test_all_worktrees_clean_allows(tmp_path):
    """Inverse: MAIN and a linked worktree both clean at completion -> ALLOW."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feature")
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)
    (wt / "feature.py").write_text("v1\n")
    subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "wt"],
                   check=True, capture_output=True)   # worktree now clean
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_allow(out, rc)


def test_worktree_same_path_plan_dirty_before_baseline_allows(tmp_path):
    """C4a (FIX A survives) — the linked worktree's OWN docs/plans/<same>.md,
    dirty BEFORE arming and untouched, is in the baseline (keyed to the worktree)
    -> ALLOW. Completion is on the MAIN plan."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feature")   # has the plan too
    wt_plan = wt / "docs" / "plans" / "2026-09-02-feature.md"
    wt_plan.write_text(wt_plan.read_text() + "- [x] wt edit\n")   # dirty BEFORE arm
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                         # baseline (wt): {docs/plans/...md}
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_allow(out, rc)


def test_worktree_same_path_plan_dirtied_after_baseline_blocks(tmp_path):
    """C4b — the SAME worktree plan copy dirtied AFTER arming is NEW dirt there
    (a different physical file, not excluded by the main plan's exclusion) ->
    BLOCK. Discriminates per-worktree keying from a shared exclusion."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feature")
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                         # baseline (wt): clean
    wt_plan = wt / "docs" / "plans" / "2026-09-02-feature.md"
    wt_plan.write_text(wt_plan.read_text() + "- [x] wt edit\n")   # NEW after arm
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_block(out)


def test_parse_worktree_list_z_multi_record(tmp_path):
    """FIX B — newline-safe `-z` enumeration parse. Feeds a NUL-delimited
    `git worktree list --porcelain -z` sample with TWO records, the second of
    which has a path CONTAINING A NEWLINE (git permits it and emits it raw). The
    NUL-based parse returns both paths intact, including the embedded newline —
    the round-1 `\\n`-split enumeration would truncate that path (its worktree's
    dirt would go invisible). Loads the guard in-process so in RED (old code with
    no `_parse_worktree_list_z`) this ONE test fails on the missing attribute."""
    guard = _load_guard()
    sample = (b"worktree /repo/main\x00HEAD abc123\x00branch refs/heads/main\x00\x00"
              b"worktree /repo/has\nnewline\x00HEAD abc123\x00branch refs/heads/feat\x00\x00")
    assert guard._parse_worktree_list_z(sample) == [
        Path("/repo/main"),
        Path("/repo/has\nnewline"),
    ]


def test_short_circuits_on_first_dirty_worktree(tmp_path):
    """FIX C survives — two worktrees dirty after arming; BLOCK names exactly one
    (short-circuit on first confirmed new dirt)."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt1 = tmp_path / "wt1"
    wt2 = tmp_path / "wt2"
    _add_worktree(main, wt1, "feat1")
    _add_worktree(main, wt2, "feat2")
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                         # baseline: all clean
    (wt1 / "a.py").write_text("v1\n")
    (wt2 / "b.py").write_text("v1\n")
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_block(out)
    assert out.count("Worktree:") == 1


def test_same_path_tristate(tmp_path):
    """P2 — `_same_path` is tri-state: True (raw-equal OR resolved-equal), False
    (both resolve and genuinely differ), None (resolve raises + raw differ). The
    None branch IS the fix: the OLD `_same_path` returned False on a resolve
    error, which made an owning worktree look like a non-owner and manufactured a
    false BLOCK on a clean completion (Codex P2). RED under the old bool
    `_same_path`: the last assertion expects None but the old code returns False.
    Uses a REAL symlink loop (no mock) to make `.resolve()` genuinely raise."""
    guard = _load_guard()
    p = tmp_path / "x"
    p.mkdir()
    assert guard._same_path(p, p) is True            # raw-equal
    link = tmp_path / "link"
    link.symlink_to(p)
    assert guard._same_path(link, p) is True         # resolved-equal (symlink)
    q = tmp_path / "y"
    q.mkdir()
    assert guard._same_path(p, q) is False           # both resolve, genuinely differ
    loop_a = tmp_path / "loop_a"
    loop_b = tmp_path / "loop_b"
    loop_a.symlink_to(loop_b)
    loop_b.symlink_to(loop_a)                         # real symlink cycle
    assert guard._same_path(loop_a, q) is None       # resolve raises + raw differ


# ---------------------------------------------------------------------------
# GROUP H — in-process unit tests (load via _load_guard())
# ---------------------------------------------------------------------------


def test_baseline_serialize_roundtrip(tmp_path):
    """H1: a v3 baseline (per-worktree {reg, paths}) with a space and a non-ASCII
    path round-trips through _read_baseline to the exact per-worktree structure.
    Renames are never recorded (never grandfathered). Writes to the guard's own
    computed path."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(plan_root, plan_rel)
    payload = {"version": guard._BASELINE_VERSION, "plan_root": str(plan_root),
               "plan_rel": plan_rel, "armed_ts": 1.0,
               "worktrees": {
                   "/abs/main": {"reg": 42, "paths": ["a b.txt", "café/x.py"]},
                   "/abs/wt": {"reg": None, "paths": []}}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        got = guard._read_baseline(plan_root, plan_rel)
    finally:
        path.unlink()
    assert got == {
        "/abs/main": {"reg": 42, "paths": {"a b.txt", "café/x.py"}},
        "/abs/wt": {"reg": None, "paths": set()}}


def test_read_baseline_corrupt_returns_none(tmp_path):
    """H1b: a non-JSON sidecar -> None (Decision 2: caller then ALLOWs)."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(plan_root, plan_rel)
    path.write_text("{not json", encoding="utf-8")
    try:
        assert guard._read_baseline(plan_root, plan_rel) is None
    finally:
        path.unlink()


def test_read_baseline_structurally_invalid_returns_none(tmp_path):
    """Finding 5: a valid-JSON baseline with a NON-STRING path element is
    REJECTED whole (None -> fail-open), never salvaged into a partial set that
    could falsely BLOCK."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(plan_root, plan_rel)
    payload = {"version": guard._BASELINE_VERSION, "plan_root": str(plan_root),
               "plan_rel": plan_rel, "armed_ts": 1.0,
               "worktrees": {"/abs/main": {"reg": 1, "paths": ["ok.py", 123],
                                           "renames": []}}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert guard._read_baseline(plan_root, plan_rel) is None
    finally:
        path.unlink()


def test_read_baseline_wrong_plan_rel_returns_none(tmp_path):
    """Findings 3 & 5: a baseline whose stored plan_rel differs from the plan
    being completed is rejected (None -> fail-open) — a sidecar for a DIFFERENT
    plan at the same hashed key must not be trusted."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    path = guard._baseline_file_path(plan_root, "docs/plans/f.md")
    payload = {"version": guard._BASELINE_VERSION, "plan_root": str(plan_root),
               "plan_rel": "docs/plans/OTHER.md", "armed_ts": 1.0,
               "worktrees": {"/abs/main": {"reg": 1, "paths": [], "renames": []}}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert guard._read_baseline(plan_root, "docs/plans/f.md") is None
    finally:
        path.unlink()


def test_read_baseline_wrong_version_returns_none(tmp_path):
    """Finding 5: a wrong schema version -> None (fail-open), never a mis-parsed
    partial set."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(plan_root, plan_rel)
    payload = {"version": 999, "plan_root": str(plan_root), "plan_rel": plan_rel,
               "armed_ts": 1.0, "worktrees": {"/abs/main": []}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert guard._read_baseline(plan_root, plan_rel) is None
    finally:
        path.unlink()


def test_write_baseline_invalidates_stale_on_failed_rearm(tmp_path):
    """Finding 1: a genuine re-arming INVALIDATES the prior sidecar BEFORE
    capture, so a capture failure leaves NO baseline (fail-open), never a stale
    one. Forces the capture failure with a real non-git dir (no mock)."""
    guard = _load_guard()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "seed").write_text("1\n")
    _commit_all(repo)   # give the repo a HEAD
    (repo / "docs" / "plans").mkdir(parents=True)
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(repo, plan_rel)
    try:
        guard._write_baseline(repo, plan_rel, repo)        # first arm -> sidecar written
        assert path.exists()
        # A REAL non-git dir. tmp_path is rooted under the coding-team repo
        # (conftest basetemp = .pytest-tmp/<pid>/), so a subdir of tmp_path is
        # still inside a git repo and enumeration would SUCCEED; mkdtemp() lands
        # in the system temp, genuinely outside any repo — the same dodge
        # test_plan_file_not_in_any_repo_allows uses.
        non_git = Path(tempfile.mkdtemp())                 # enumeration fails here
        guard._write_baseline(repo, plan_rel, non_git)     # failed re-arm
        assert not path.exists()                           # stale baseline is GONE
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def test_filter_new_set_semantics():
    """H2: residual = non-rename paths not in baseline_paths, PLUS every rename/
    copy entry ALWAYS (renames are never grandfathered — Codex round-3). Path-only
    for non-renames (Decision 1)."""
    guard = _load_guard()
    entries = [(" M", "a", ""), ("??", "b", ""), (" M", "c", "")]
    assert guard._filter_new(entries, {"a", "c"}) == [("??", "b", "")]
    # re-edit: non-rename path 'a' is in baseline -> subtracted (path-only)
    assert guard._filter_new([("MM", "a", "")], {"a"}) == []
    # a rename is ALWAYS kept, even when its dest path is in baseline_paths.
    assert guard._filter_new([("R ", "other.py", "src.py")], {"other.py"}) \
        == [("R ", "other.py", "src.py")]
    # a worktree-column rename (' R') is likewise never subtracted.
    assert guard._filter_new([(" R", "d.py", "s.py")], {"d.py", "s.py"}) \
        == [(" R", "d.py", "s.py")]


def test_is_arming_transition(tmp_path):
    """H3: the arming detector across Edit, Write, and non-/re-arm transitions —
    including complete->in-progress (arms) and ambiguous PRE (does NOT arm)."""
    guard = _load_guard()
    plan = tmp_path / "p.md"
    plan.write_text("---\nstatus: planned\n---\n\n# Plan\n")
    edit = {"file_path": str(plan), "old_string": "status: planned",
            "new_string": "status: in-progress"}
    assert guard._is_arming_transition("Edit", edit, plan) is True
    # planned -> planned (checkbox) is not arming
    noop = {"file_path": str(plan), "old_string": "# Plan", "new_string": "# Plan\n- x"}
    assert guard._is_arming_transition("Edit", noop, plan) is False
    # in-progress PRE -> not a fresh arming
    plan.write_text("---\nstatus: in-progress\n---\n\n# Plan\n")
    reflip = {"file_path": str(plan), "old_string": "status: in-progress",
              "new_string": "status: in-progress"}
    assert guard._is_arming_transition("Edit", reflip, plan) is False
    # in-progress -> complete is not arming
    comp = {"file_path": str(plan), "old_string": "status: in-progress",
            "new_string": "status: complete"}
    assert guard._is_arming_transition("Edit", comp, plan) is False
    # complete -> in-progress (reopen) IS a fresh (re-)arming (Finding 2a)
    plan.write_text("---\nstatus: complete\n---\n\n# Plan\n")
    reopen = {"file_path": str(plan), "old_string": "status: complete",
              "new_string": "status: in-progress"}
    assert guard._is_arming_transition("Edit", reopen, plan) is True
    # ambiguous PRE (duplicate status key) -> NOT arming (Finding 2b)
    plan.write_text("---\nstatus: complete\nstatus: complete\n---\n\n# Plan\n")
    ambig = {"file_path": str(plan), "old_string": "# Plan",
             "new_string": "---\nstatus: in-progress\n---\n# Plan"}
    assert guard._is_arming_transition("Edit", ambig, plan) is False
    # absent file Written directly to in-progress IS arming
    absent = tmp_path / "new.md"
    write = {"file_path": str(absent),
             "content": "---\nstatus: in-progress\n---\n\n# Plan\n"}
    assert guard._is_arming_transition("Write", write, absent) is True


# ---------------------------------------------------------------------------
# GROUP A — end-to-end arming capture
# ---------------------------------------------------------------------------


def test_arming_with_dirty_tree_allows_and_writes_baseline(tmp_path):
    """A1: arming with pre-existing junk ALLOWS and records both dirty paths."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "old.py").write_text("v1\n")
    _commit_all(repo)                       # plan + old.py committed, tree clean
    (repo / "junk.txt").write_text("x\n")   # pre-existing untracked
    (repo / "old.py").write_text("v2\n")    # pre-existing modification
    env = _tmpdir_env(tmp_path)
    out, rc = _run(_edit_planned_to_in_progress(plan), cwd=repo, env=env)
    _assert_allow(out, rc)
    data = json.loads(_the_sidecar(env).read_text())
    all_paths = [p for wt in data["worktrees"].values() for p in wt["paths"]]
    assert "junk.txt" in all_paths and "old.py" in all_paths


def test_arming_excludes_plan_file_from_baseline(tmp_path):
    """A2: the plan file's own mid-edit dirt is excluded at CAPTURE time too."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    plan.write_text(plan.read_text() + "- [x] tick\n")   # dirty ONLY the plan
    env = _tmpdir_env(tmp_path)
    out, rc = _run(_edit_planned_to_in_progress(plan), cwd=repo, env=env)
    _assert_allow(out, rc)
    data = json.loads(_the_sidecar(env).read_text())
    all_paths = [p for wt in data["worktrees"].values() for p in wt["paths"]]
    assert not any("2026-09-02-feature.md" in p for p in all_paths)


def test_complete_to_in_progress_reopen_rearms_fresh(tmp_path):
    """Finding 2a (capture-side, valid in Task 1) — a complete -> in-progress
    reopen is a FRESH re-arming that REPLACES the prior baseline (not a union).
    Arm with junkX; set the plan complete; swap junkX->junkY; reopen -> the
    sidecar is {junkY} only. Sidecar-only assertion, so it is meaningful even
    while the completion path is still the old whole-tree logic."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    (repo / "junkX.txt").write_text("x\n")
    _arm(plan, repo, env)                    # baseline = {junkX.txt}
    plan.write_text(plan.read_text().replace("status: in-progress", "status: complete", 1))
    (repo / "junkX.txt").unlink()
    (repo / "junkY.txt").write_text("y\n")
    out, rc = _run({"tool_name": "Edit", "tool_input": {
        "file_path": str(plan), "old_string": "status: complete",
        "new_string": "status: in-progress"}}, cwd=repo, env=env)
    _assert_allow(out, rc)
    data = json.loads(_the_sidecar(env).read_text())
    allp = [p for wt in data["worktrees"].values() for p in wt["paths"]]
    assert any("junkY.txt" in p for p in allp)
    assert not any("junkX.txt" in p for p in allp)   # replaced, not unioned


# ---------------------------------------------------------------------------
# SAFETY floor + anti-re-trap + documented leak (Step 2.4)
# ---------------------------------------------------------------------------


def test_preexisting_junk_present_before_arming_allows_completion(tmp_path):
    """SAFETY-1 — the whole point. Cross-session junk that predates the run and
    is untouched by it no longer blocks completion. RED against today's hook
    (which blocks on any dirt); GREEN only after baseline subtraction."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "unrelated.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "stray.txt").write_text("x\n")        # pre-existing untracked
    (repo / "unrelated.py").write_text("v2\n")    # pre-existing modification
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                         # baseline = {stray.txt, unrelated.py}
    # leave the junk exactly as-is
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_new_untracked_and_new_modified_after_baseline_blocks(tmp_path):
    """SAFETY-2 — this-run's own work still blocks; message names BOTH files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "keep.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                         # baseline empty
    (repo / "feature.py").write_text("v1\n")      # NEW untracked
    (repo / "keep.py").write_text("v2\n")         # NEW modification
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)
    assert "feature.py" in out and "keep.py" in out


def test_mixed_preexisting_and_new_blocks_on_new_only(tmp_path):
    """Subtraction is per-path: residual names the new file, not the old junk."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    (repo / "stray.txt").write_text("x\n")        # pre-existing
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                         # baseline = {stray.txt}
    (repo / "feature.py").write_text("v1\n")      # NEW
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)
    assert "feature.py" in out and "stray.txt" not in out


def test_baseline_dirty_tracked_file_mutates_again_allows(tmp_path):
    """Anti-re-trap (the reason for path-only). A tracked file dirty at arming —
    stand-in for tracked telemetry like harness-*.jsonl — that MUTATES AGAIN by
    completion is ALLOWED, because its path is in the baseline. A content-hash
    baseline would RE-BLOCK here, reintroducing the trap."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "telemetry.jsonl").write_text("line1\n")
    _commit_all(repo)
    (repo / "telemetry.jsonl").write_text("line1\nline2\n")   # dirty BEFORE arming
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                         # baseline = {telemetry.jsonl}
    (repo / "telemetry.jsonl").write_text("line1\nline2\nline3\n")  # mutates AGAIN
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


@pytest.mark.xfail(strict=True, reason=(
    "path-only baseline (Decision 1): a path dirty at arming that the run "
    "re-modifies and leaves uncommitted is an ACCEPTED leak. This asserts the "
    "IDEAL (BLOCK), which path-only does not deliver; xfail keeps the hole "
    "visible. If content-hashing is ever added the assert passes -> strict "
    "xfail XPASSes -> CI flags it to update this test."))
def test_baseline_dirty_file_reedited_is_known_leak(tmp_path):
    """Re-edit hole: the run's deliverable lands on a coincidentally-dirty path,
    re-modifies it, leaves it uncommitted. IDEALLY this blocks (the run's own
    edit escapes the gate); path-only ALLOWs it. Documented, never silent."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "shared.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "shared.py").write_text("v2\n")       # pre-existing junk
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                         # baseline = {shared.py}
    (repo / "shared.py").write_text("v3-run-edit\n")   # run re-edits, uncommitted
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)   # IDEAL; path-only actually ALLOWs -> this fails -> xfail


# ---------------------------------------------------------------------------
# GROUP F — fail directions (Step 2.7)
# ---------------------------------------------------------------------------


def test_missing_baseline_allows(tmp_path):
    """F2 (Decision 2 OVERRIDE) — a plan that never armed (no sidecar) with a
    DIRTY tree ALLOWs. Missing baseline is transitional (pre-fix plans); strict
    block would re-trap them. The per-test TMPDIR is empty because _arm never
    ran, so the hook finds no sidecar."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="in-progress")   # committed in-progress, NO arming
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")           # real dirt
    env = _tmpdir_env(tmp_path)                    # empty TMPDIR -> no sidecar exists
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_corrupt_baseline_allows(tmp_path):
    """F3 (Decision 2 OVERRIDE) — a corrupt sidecar ALLOWs (same fail direction
    as missing). Arm normally, then CORRUPT the written sidecar in place (no env
    override exists — Finding 3)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                          # sidecar written
    _the_sidecar(env).write_text("{ not valid json", encoding="utf-8")   # corrupt it
    (repo / "src.py").write_text("v2\n")           # real dirt
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_wrong_plan_rel_baseline_allows(tmp_path):
    """Findings 3 & 5 (end-to-end) — a sidecar whose stored plan_rel does not
    match the plan being completed is rejected -> fail-open ALLOW, even with real
    dirt. Arm, then rewrite the sidecar's plan_rel to a different value."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    sidecar = _the_sidecar(env)
    data = json.loads(sidecar.read_text())
    data["plan_rel"] = "docs/plans/SOMETHING-ELSE.md"
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    (repo / "src.py").write_text("v2\n")           # real dirt
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_allow(out, rc)


def test_git_unavailable_at_completion_allows(tmp_path):
    """F1 — with a baseline present, a git failure at completion fails OPEN
    (ALLOW), preserving the hook's git-uncertainty contract. git is made
    unavailable by stripping PATH for the completion run only (the hook launches
    git via PATH; python itself is launched by absolute path, so the hook still
    runs and simply cannot find git)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                          # baseline written with git available
    (repo / "src.py").write_text("v2\n")           # dirt (would block if git worked)
    broken = {**env, "PATH": "/nonexistent"}       # git not found at completion
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=broken)
    _assert_allow(out, rc)


def test_rearm_overwrites_stale_baseline(tmp_path):
    """F4 — re-arming overwrites the sidecar (no union). Arm with junkX; reset
    the plan to planned and swap junkX->junkY; arm again; the baseline reflects
    Y only, proving X was not carried forward."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    (repo / "junkX.txt").write_text("x\n")
    _arm(plan, repo, env)                          # baseline = {junkX.txt}
    data1 = json.loads(_the_sidecar(env).read_text())
    assert any("junkX.txt" in p for wt in data1["worktrees"].values() for p in wt["paths"])
    # simulate a reset: plan back to planned, swap the junk
    plan.write_text(plan.read_text().replace("status: in-progress", "status: planned", 1))
    (repo / "junkX.txt").unlink()
    (repo / "junkY.txt").write_text("y\n")
    _arm(plan, repo, env)                          # re-arm -> baseline = {junkY.txt}
    data2 = json.loads(_the_sidecar(env).read_text())
    all2 = [p for wt in data2["worktrees"].values() for p in wt["paths"]]
    assert any("junkY.txt" in p for p in all2)
    assert not any("junkX.txt" in p for p in all2)   # NOT a union


# ---------------------------------------------------------------------------
# Codex-finding tests (baseline-aware; Step 2.10)
# ---------------------------------------------------------------------------


def test_rename_onto_baselined_path_blocks(tmp_path):
    """Finding 4 — a rename/copy is NEVER subtracted, even when its DEST path is
    in the baseline. baseline has untracked other.py; the run `git mv -f`s src.py
    onto other.py; the rename dest matches a baseline path but is real work ->
    BLOCK. Under a naive path-only subtraction this ALLOWs (the leak)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "other.py").write_text("junk\n")       # pre-existing untracked
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                          # baseline = {other.py}
    subprocess.run(["git", "-C", str(repo), "mv", "-f", "src.py", "other.py"],
                   check=True, capture_output=True)   # rename dest == baselined path
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_absent_write_direct_to_in_progress_arms_end_to_end(tmp_path):
    """Finding 2 (end-to-end) — a NEW plan Written straight to in-progress (PRE
    absent) arms: pre-existing junk is captured, so at completion the junk is
    grandfathered (ALLOW) but the run's NEW work still BLOCKS."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "docs" / "plans").mkdir(parents=True)
    (repo / "seed").write_text("1\n")
    _commit_all(repo)
    (repo / "junk.txt").write_text("x\n")          # pre-existing junk at arming
    plan = repo / "docs" / "plans" / "new.md"      # does NOT exist yet
    content = "---\nstatus: in-progress\n---\n\n# Plan\n"
    env = _tmpdir_env(tmp_path)
    out, rc = _run({"tool_name": "Write", "tool_input": {
        "file_path": str(plan), "content": content}}, cwd=repo, env=env)
    _assert_allow(out, rc)                          # arming ALLOWs
    data = json.loads(_the_sidecar(env).read_text())
    assert any("junk.txt" in p for wt in data["worktrees"].values() for p in wt["paths"])
    plan.write_text(content)                        # the real Write lands the file
    (repo / "feature.py").write_text("v1\n")        # NEW work after arming
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)
    assert "feature.py" in out and "junk.txt" not in out


def test_ambiguous_pre_edit_does_not_resnapshot(tmp_path):
    """Finding 2b (end-to-end) — a mid-run edit whose PRE frontmatter is
    AMBIGUOUS (duplicate status key) must NOT re-snapshot the run's OWN dirt as
    baseline. Arm clean; create run dirt; fire an in-progress-ish edit over a
    malformed plan on disk; the baseline is unchanged, so the run's dirt still
    BLOCKS at completion."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                          # baseline empty (clean)
    before = _the_sidecar(env).read_text()
    (repo / "feature.py").write_text("v1\n")       # the run's OWN work
    # Corrupt the plan frontmatter on disk (duplicate status key) and fire an
    # edit that would look like an arming to a naive detector.
    plan.write_text("---\nstatus: in-progress\nstatus: in-progress\n---\n\n# Plan\n")
    out, rc = _run({"tool_name": "Edit", "tool_input": {
        "file_path": str(plan), "old_string": "# Plan",
        "new_string": "# Plan\n- x"}}, cwd=repo, env=env)
    _assert_allow(out, rc)                          # neither a (re)arm nor a completion
    assert _the_sidecar(env).read_text() == before  # baseline untouched
    # Restore a clean in-progress plan and complete -> the run's dirt still blocks.
    plan.write_text("---\nstatus: in-progress\n---\n\n# Plan\n")
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)
    assert "feature.py" in out


# ---------------------------------------------------------------------------
# Codex review round 2 — P1 (rename in EITHER porcelain column) + P2 + P3
# ---------------------------------------------------------------------------


def test_worktree_rename_second_column_not_subtracted_blocks(tmp_path):
    """P1 (Codex BLOCKING repro) — a WORKING-TREE rename shows R in the SECOND
    porcelain column (' R'), a 2-path NUL record `\\x20R b\\0xxxc\\0`. Both the
    rename dest `b` and an untracked `c` are baselined. A parser that checks only
    the FIRST column misparses the record (drops the orig field, invents an entry
    for `c`) and then subtracts everything -> wrongly ALLOWS an uncommitted
    rename. Renames/copies are NEVER subtracted, so this MUST BLOCK. Reproduces
    Codex's exact steps: mv committed xxxc onto b, `git add -N b`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "xxxc").write_text("committed\n")
    _commit_all(repo)                              # xxxc tracked/clean
    (repo / "b").write_text("junkb\n")             # untracked, baselined
    (repo / "c").write_text("junkc\n")             # untracked, baselined
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                          # baseline = {b, c}
    (repo / "b").unlink()                          # make room for the rename dest
    os.rename(repo / "xxxc", repo / "b")           # committed source moved onto b
    subprocess.run(["git", "-C", str(repo), "add", "-N", "b"],
                   check=True, capture_output=True)  # intent-to-add -> ' R b\0xxxc'
    # Sanity: git really put R in the SECOND column (a 2-path worktree rename).
    porc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "-z", "--untracked-files=all"],
        capture_output=True, check=True).stdout
    assert b"\x20R b\x00xxxc\x00" in porc, f"unexpected porcelain: {porc!r}"
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)                             # rename is real work, never subtracted


def test_version_true_baseline_fails_open(tmp_path):
    """P2.1 (Codex) — JSON `true` for version must NOT be accepted (Python
    True == 1). A `{"version": true, ...}` sidecar is corrupt; it must resolve to
    None -> fail-open ALLOW, NOT be consumed as a valid-but-empty baseline (which
    would then BLOCK pre-existing dirt). Unit-level on _read_baseline."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(plan_root, plan_rel)
    payload = {"version": True, "plan_root": str(plan_root), "plan_rel": plan_rel,
               "armed_ts": 1.0, "worktrees": {"/abs/main": []}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert guard._read_baseline(plan_root, plan_rel) is None
    finally:
        path.unlink()


def test_version_float_baseline_fails_open(tmp_path):
    """P2.1 (Codex) — JSON `1.0` (float) must NOT be accepted either (1.0 == 1).
    Corrupt -> None -> fail-open ALLOW."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    path = guard._baseline_file_path(plan_root, plan_rel)
    payload = {"version": 1.0, "plan_root": str(plan_root), "plan_rel": plan_rel,
               "armed_ts": 1.0, "worktrees": {"/abs/main": []}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert guard._read_baseline(plan_root, plan_rel) is None
    finally:
        path.unlink()


def test_worktree_recreated_at_same_path_does_not_inherit_baseline(tmp_path):
    """P2.2 (Codex) — a worktree removed and RE-CREATED at the SAME path is a new
    registration (git reuses the path and even the admin-dir NAME, but the admin
    gitdir gets a NEW inode). Its baseline entry must NOT be inherited by path
    alone, or new uncommitted work at the same repo-relative path is subtracted
    -> ALLOWS new work. With registration-identity keying the new worktree has an
    empty baseline -> its dirt BLOCKS (fail-safe)."""
    main = tmp_path / "repo"
    main.mkdir()
    _init_repo(main)
    plan = _make_plan(main, status="planned")
    _commit_all(main)
    wt = tmp_path / "wt"
    _add_worktree(main, wt, "feat")
    (wt / "shared.txt").write_text("old junk\n")   # dirty at arming (baselined)
    env = _tmpdir_env(tmp_path)
    _arm(plan, main, env)                          # baseline (wt reg A): {shared.txt}
    subprocess.run(["git", "-C", str(main), "worktree", "remove", "--force", str(wt)],
                   check=True, capture_output=True)
    _add_worktree(main, wt, "feat2")               # SAME path, new registration/inode
    (wt / "shared.txt").write_text("NEW run work\n")  # new uncommitted, same rel path
    out, rc = _run(_edit_to_complete(plan), cwd=main, env=env)
    _assert_block(out)                             # must not inherit the old allow-set
    assert "shared.txt" in out


def test_unremovable_stale_sidecar_on_failed_rearm_does_not_grandfather(tmp_path):
    """P2.3 (Codex) — a failed re-arm must not leave a VALID stale sidecar that
    completion then trusts (grandfathering new work on a stale-baselined path).
    Real repro, no mocks: arm run #1 with `shared.txt` baselined; make the TMPDIR
    READ-ONLY so a re-arm can neither unlink nor create-anew in it; re-arm run #2
    while `shared.txt` is CLEAN (its intended baseline is empty) with enumeration
    forced to fail -> the write side must render the un-removable sidecar UNUSABLE
    (invalidate content, which needs only file-write perm, not dir-write). Then a
    completion with NEW work at `shared.txt` must NOT be grandfathered: no usable
    baseline -> fail-open ALLOW is fine, but stale SUBTRACTION (a targeted leak)
    is not — asserted by proving the sidecar no longer parses as a valid baseline
    holding shared.txt."""
    guard = _load_guard()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "seed").write_text("1\n")
    _commit_all(repo)
    (repo / "docs" / "plans").mkdir(parents=True)
    plan_rel = "docs/plans/f.md"
    non_git = Path(tempfile.mkdtemp())             # real non-repo; enumeration fails here
    iso = tmp_path / "iso"
    iso.mkdir()
    orig_iso_mode = os.stat(iso).st_mode
    orig_tempdir = tempfile.tempdir
    tempfile.tempdir = str(iso)                     # redirect gettempdir() -> isolated dir
    path = None
    try:
        path = guard._baseline_file_path(repo, plan_rel)   # now under iso
        (repo / "shared.txt").write_text("old\n")  # dirty -> run #1 baselines it
        guard._write_baseline(repo, plan_rel, repo)
        data = json.loads(path.read_text())
        assert any("shared.txt" in p for wt in data["worktrees"].values() for p in wt["paths"])
        # Freeze the sidecar's dir: unlink/create in it now fail (EACCES) but a
        # file-content overwrite (we own the file) still works — the fix must use
        # that to render the un-removable sidecar unusable on a failed re-arm.
        os.chmod(iso, 0o500)
        try:
            guard._write_baseline(repo, plan_rel, non_git)   # failed re-arm (enum None)
        finally:
            os.chmod(iso, orig_iso_mode)           # restore so we can read/clean
        # The stale sidecar must NOT still be a valid baseline holding shared.txt.
        assert guard._read_baseline(repo, plan_rel) is None, (
            "failed re-arm left a valid stale baseline -> would grandfather new work"
        )
    finally:
        tempfile.tempdir = orig_tempdir
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Codex review round 3 — rename grandfather, None-key, symlink-safe I/O
# ---------------------------------------------------------------------------


def test_preexisting_rename_at_arming_blocks_documented_limitation(tmp_path):
    """Round-3 (Codex) — rename/copy entries are NEVER grandfathered. A rename
    that already existed UNCHANGED at arming still BLOCKS at completion: an
    accepted, documented, safe-direction limitation (chosen over content
    fingerprinting to keep the gate provably leak-free). A lingering uncommitted
    rename at arming is rare; the block is the safe direction — commit or discard
    it. Plain untracked junk is unaffected (still grandfathered via path)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    subprocess.run(["git", "-C", str(repo), "mv", "src.py", "other.py"],
                   check=True, capture_output=True)   # rename BEFORE arming
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)
    # no further change — but a rename is never grandfathered
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_modified_preexisting_rename_restaged_blocks(tmp_path):
    """Round-3 P1 (Codex, reproduced) — a rename staged BEFORE arming, then
    MODIFIED (small change) and re-staged during the run, keeps the IDENTICAL
    porcelain tuple `R  dest\\0src`, so a (status,dest,source) baseline match
    would wrongly subtract it -> ALLOW uncommitted run work. Renames are never
    grandfathered -> BLOCK. Uses an 8-line file + a one-line append so git's
    rename detection still fires (the tuple stays R, unchanged)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("".join(f"line{n}\n" for n in range(1, 9)))
    _commit_all(repo)
    subprocess.run(["git", "-C", str(repo), "mv", "src.py", "dest.py"],
                   check=True, capture_output=True)   # staged rename BEFORE arming
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                             # rename present at arming
    (repo / "dest.py").write_text(
        "".join(f"line{n}\n" for n in range(1, 9)) + "ADDED\n")   # small modify
    subprocess.run(["git", "-C", str(repo), "add", "dest.py"],
                   check=True, capture_output=True)   # re-stage -> tuple unchanged
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_new_rename_after_arming_blocks(tmp_path):
    """FIX 1(b) — a rename created AFTER arming is new work with no matching
    baseline record -> BLOCK."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo, status="planned")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    env = _tmpdir_env(tmp_path)
    _arm(plan, repo, env)                             # clean baseline (no renames)
    subprocess.run(["git", "-C", str(repo), "mv", "src.py", "other.py"],
                   check=True, capture_output=True)   # NEW rename after arming
    out, rc = _run(_edit_to_complete(plan), cwd=repo, env=env)
    _assert_block(out)


def test_null_registration_baseline_does_not_false_block(tmp_path):
    """FIX 2 — a baseline worktree entry whose registration id is null (identity
    unknown at ARMING) must make that worktree's baseline UNAVAILABLE at
    completion -> fail-open (skip), NEVER a permanent false-block of pre-existing
    dirt (the old `<path>\\0None` key would miss the lookup and block forever)."""
    guard = _load_guard()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "seed").write_text("1\n")
    _commit_all(repo)
    (repo / "pre.txt").write_text("junk\n")          # pre-existing dirt at completion
    resolved = str(repo.resolve())
    baseline = {resolved: {"reg": None, "paths": {"pre.txt"}}}
    result = guard._collect_new_dirt_across_worktrees(repo, "docs/plans/x.md", baseline)
    assert result == {}, f"null-reg baseline must fail-open (skip), got {result!r}"


def test_symlinked_sidecar_not_followed_on_read(tmp_path):
    """FIX 3 — the sidecar read uses O_NOFOLLOW: a symlink at the sidecar path
    pointing at an otherwise-valid baseline is NOT followed -> None -> fail-open,
    closing a symlink-swap that could feed a permissive foreign baseline."""
    guard = _load_guard()
    plan_root = tmp_path / "root"
    plan_rel = "docs/plans/f.md"
    sidecar = guard._baseline_file_path(plan_root, plan_rel)
    target = tmp_path / "target.json"
    # A well-formed baseline for the pre-fix (v1 list) schema, so that FOLLOWING
    # the symlink would return non-None under the pre-fix reader — proving the
    # O_NOFOLLOW read (not a schema quirk) is what rejects it. Post-fix the
    # O_NOFOLLOW open fails first, so None holds regardless of schema/version.
    payload = {"version": 1, "plan_root": str(plan_root), "plan_rel": plan_rel,
               "armed_ts": 1.0, "worktrees": {"/abs/main": ["x"]}}
    target.write_text(json.dumps(payload), encoding="utf-8")
    sidecar.symlink_to(target)
    try:
        assert guard._read_baseline(plan_root, plan_rel) is None
    finally:
        sidecar.unlink()
        target.unlink()


def test_symlinked_sidecar_write_does_not_clobber_target(tmp_path):
    """FIX 3 — invalidation's content-overwrite fallback uses O_NOFOLLOW, so a
    symlink at the sidecar path is not followed to clobber its target. Force the
    unlink to fail (read-only dir) so invalidation reaches the content-write; the
    symlink target must be untouched."""
    guard = _load_guard()
    iso = tmp_path / "iso"
    iso.mkdir()
    orig_tempdir = tempfile.tempdir
    tempfile.tempdir = str(iso)
    sidecar = None
    target = tmp_path / "target.txt"
    target.write_text("PRECIOUS\n")
    try:
        plan_root = tmp_path / "root"
        plan_rel = "docs/plans/f.md"
        sidecar = guard._baseline_file_path(plan_root, plan_rel)
        sidecar.symlink_to(target)
        mode = os.stat(iso).st_mode
        os.chmod(iso, 0o500)                          # unlink in iso now fails
        try:
            guard._invalidate_sidecar(sidecar)        # falls to content-write
        finally:
            os.chmod(iso, mode)
        assert target.read_text() == "PRECIOUS\n", "O_NOFOLLOW must block the clobber"
    finally:
        tempfile.tempdir = orig_tempdir
        if sidecar is not None:
            try:
                sidecar.unlink()
            except OSError:
                pass
        try:
            target.unlink()
        except OSError:
            pass
