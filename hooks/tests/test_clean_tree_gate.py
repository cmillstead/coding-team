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
    plan = _make_plan(repo)
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)                      # tree clean, plan committed in-progress
    (repo / "src.py").write_text("v2\n")   # uncommitted tracked modification
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_block(out)


def test_transition_with_untracked_file_blocks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)
    _commit_all(repo)
    (repo / "new.txt").write_text("x\n")   # untracked, non-ignored
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_block(out)


def test_transition_clean_tree_allows_and_excludes_plan(tmp_path):
    """Only the plan file is dirty in porcelain -> exclusion makes the tree
    'clean' -> ALLOW. Without exclusion this would BLOCK.

    NOTE: a plan file showing up in porcelain is REAL for this tmp test repo
    (which tracks docs/plans), and for any downstream coding-team PROJECT that
    tracks docs/plans. It does NOT happen in coding-team's OWN repo, where
    docs/plans is gitignored. So the plan-file exclusion is load-bearing for
    those downstream projects — it is not dead code to 'simplify' away just
    because this harness never exercises it in production."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)
    _commit_all(repo)                      # plan committed in-progress, tree clean
    # Dirty ONLY the plan file (append a checkbox tick; status stays in-progress).
    plan.write_text(plan.read_text() + "- [x] tick\n")
    porcelain = _porcelain(repo)
    assert porcelain.strip() != "" and "docs/plans/" in porcelain  # plan IS dirty
    assert porcelain.count("\n") == 1                              # ONLY the plan
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_allow(out, rc)


def test_transition_only_gitignored_dirty_allows(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / ".gitignore").write_text("ignored.txt\n")
    plan = _make_plan(repo)
    _commit_all(repo)
    (repo / "ignored.txt").write_text("junk\n")  # dirty but gitignored
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
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
    """A Write (not Edit) flipping the plan to complete + dirty tree -> BLOCK.
    Exercises the Write branch of _post_edit_content (uses `content`)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)                # in-progress on disk
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")   # dirty
    event = {"tool_name": "Write", "tool_input": {
        "file_path": str(plan),
        "content": "---\nstatus: complete\n---\n\n# Plan\n",
    }}
    out, rc = _run(event, cwd=repo)
    _assert_block(out)


def test_replace_all_completion_transition_with_dirty_tree_blocks(tmp_path):
    """replace_all discriminator (FIX 10): the frontmatter has a DECOY
    `note: in-progress` BEFORE the real `status: in-progress`. The Edit replaces
    'in-progress' -> 'complete' with replace_all: true. A single-replacement impl
    would change only the decoy `note` (status stays in-progress -> non-transition
    -> ALLOW, which FAILS this BLOCK expectation); correct replace_all flips BOTH,
    so status becomes complete -> transition -> BLOCK on the dirty tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plans = repo / "docs" / "plans"
    plans.mkdir(parents=True)
    plan = plans / "feature.md"
    plan.write_text("---\nnote: in-progress\nstatus: in-progress\n---\n\n# Plan\n")
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")   # dirty
    event = {"tool_name": "Edit", "tool_input": {
        "file_path": str(plan),
        "old_string": "in-progress",
        "new_string": "complete",
        "replace_all": True,
    }}
    out, rc = _run(event, cwd=repo)
    _assert_block(out)


def test_transition_plan_only_untracked_in_docs_allows(tmp_path):
    """Plan is the ONLY dirty thing and lives in an otherwise-untracked docs/
    (nothing committed under docs/). With `--untracked-files=all` the plan is
    listed individually and excluded -> ALLOW. Default porcelain collapses it to
    `?? docs/`, which cannot be excluded -> would wrongly BLOCK (TRAPs without
    FIX 2)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README").write_text("x\n")
    _commit_all(repo)                      # HEAD exists; docs/ is fully untracked
    plan = _make_plan(repo)                # docs/plans/...md, untracked
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_allow(out, rc)


def test_transition_plan_filename_with_space_allows(tmp_path):
    """Plan filename contains a space; only the plan is dirty. `-z` never quotes
    paths, so the porcelain path equals plan_rel and the plan is excluded ->
    ALLOW. Porcelain v1 would print `"docs/plans/my plan.md"` (quoted) != plan_rel
    -> would wrongly BLOCK (TRAPs without FIX 2)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plans = repo / "docs" / "plans"
    plans.mkdir(parents=True)
    plan = plans / "my plan.md"
    plan.write_text("---\nstatus: in-progress\n---\n\n# Plan\n")
    _commit_all(repo)                      # committed in-progress; tree clean
    plan.write_text(plan.read_text() + "- [x] tick\n")  # dirty ONLY the plan
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_allow(out, rc)


def test_transition_with_uncommitted_rename_blocks(tmp_path):
    """An uncommitted rename of a NON-plan file (R src.py -> other.py) + a
    completion transition -> BLOCK. A rename is real uncommitted work; the guard
    never excludes a rename/copy entry (closes the rename-drops-source LEAK)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)                      # tree clean
    subprocess.run(["git", "-C", str(repo), "mv", "src.py", "other.py"],
                   check=True, capture_output=True)  # staged rename, uncommitted
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_block(out)


def test_transition_git_env_poisoned_still_blocks(tmp_path):
    """FIX 8: an ambient GIT_DIR/GIT_WORK_TREE pointing at a CLEAN decoy repo must
    NOT redirect the guard's `git status` away from the dirty target repo. The
    status subprocess scrubs GIT_* (via _scrub_git_env), so the completion still
    BLOCKs. Without the scrub, git would inspect the clean decoy -> dirty empty ->
    ALLOW -> LEAK (the ambient-env-corrupts-verification failure class)."""
    target = tmp_path / "target"
    target.mkdir()
    _init_repo(target)
    plan = _make_plan(target)
    (target / "src.py").write_text("v1\n")
    _commit_all(target)
    (target / "src.py").write_text("v2\n")   # target is DIRTY
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    _init_repo(decoy)
    (decoy / "keep.txt").write_text("x\n")
    _commit_all(decoy)                        # decoy is CLEAN
    poisoned = {"GIT_DIR": str(decoy / ".git"), "GIT_WORK_TREE": str(decoy)}
    out, rc = _run(_edit_to_complete(plan), cwd=target, env=poisoned)
    _assert_block(out)


def test_transition_rename_to_plan_dest_blocks(tmp_path):
    """FIX 11: a rename whose DESTINATION is the plan file is still real dirt (the
    source moved) and must NOT be excluded. Commit a non-plan source carrying real
    in-progress plan text, `git mv` it to docs/plans/feature.md (dest == plan_rel),
    then send the completion edit against that dest with no other dirt -> BLOCK.
    Proves the rename/copy branch is never wrongly excluded even when dest==plan."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "src_plan.md").write_text("---\nstatus: in-progress\n---\n\n# Plan\n")
    _commit_all(repo)                        # tree clean; source committed
    (repo / "docs" / "plans").mkdir(parents=True)  # git mv needs the dest dir
    subprocess.run(["git", "-C", str(repo), "mv", "src_plan.md", "docs/plans/feature.md"],
                   check=True, capture_output=True)  # staged rename, dest == plan
    plan = repo / "docs" / "plans" / "feature.md"
    out, rc = _run(_edit_to_complete(plan), cwd=repo)
    _assert_block(out)


def test_parse_porcelain_z_multi_record_alignment():
    """Unit test for _parse_porcelain_z (FIX 11): a rename record (two NUL fields,
    dest first) FOLLOWED by an ordinary entry must parse to EXACTLY two entries
    with correct alignment — the rename must not swallow the following entry, and
    the trailing NUL must not produce a phantom entry. Loads the guard in-process
    (so in RED this ONE test fails with FileNotFoundError, not the whole module)."""
    guard = _load_guard()
    stream = b"R  docs/plans/feature.md\x00old_src.md\x00 M src.py\x00"
    assert guard._parse_porcelain_z(stream) == [
        ("R ", "docs/plans/feature.md"),
        (" M", "src.py"),
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


def test_dispatcher_routes_completion_transition_to_clean_tree_gate(tmp_path):
    """A dirty-tree completion transition, sent through the DISPATCHER, blocks."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")  # dirty
    result = subprocess.run(
        [sys.executable, str(DISPATCHER)],
        input=json.dumps(_edit_to_complete(plan)),
        capture_output=True, text=True, timeout=10, cwd=str(repo),
    )
    assert '"decision": "block"' in result.stdout


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
    """Ordering discriminator (FIX 7): a Write completion transition whose plan
    content carries path tokens makes write-guard emit a NON-blocking C1 allow-
    advisory. Because clean-tree runs BEFORE write-guard in the dispatcher, the
    dirty completion is still BLOCKED. If the order were reversed, write-guard's
    advisory stdout would win (first-response-wins) and the dirty completion
    would LEAK — so this test fails under the wrong order."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    plan = _make_plan(repo)
    (repo / "src.py").write_text("v1\n")
    _commit_all(repo)
    (repo / "src.py").write_text("v2\n")  # dirty
    # Full plan body with path tokens (docs/plans/..., path.resolve()) -> triggers
    # write-guard's language-agnostic C1 path-trust ALLOW advisory on this edit.
    content = ("---\nstatus: complete\n---\n\n# Plan\n\n"
               "See docs/plans/feature.md and call path.resolve() here.\n")
    result = subprocess.run(
        [sys.executable, str(DISPATCHER)],
        input=json.dumps({"tool_name": "Write", "tool_input": {
            "file_path": str(plan), "content": content}}),
        capture_output=True, text=True, timeout=10, cwd=str(repo),
    )
    assert '"decision": "block"' in result.stdout
