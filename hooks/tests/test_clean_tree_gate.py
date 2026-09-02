"""Tests for clean-tree-gate.py hook — the plan-completion clean-tree guard.

Each test builds a fresh real git repo (no mocks) and runs the hook via
subprocess with a JSON event on stdin, mirroring production invocation.
"""
import importlib.util
import subprocess
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
