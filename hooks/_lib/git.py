"""Git command parsing utilities for Claude Code hooks."""

import os
import re
import shlex
import subprocess
from pathlib import Path


def extract_cd_target(command: str) -> str | None:
    """Extract the directory from a leading `cd <path>` in a bash command.

    The harness runs git as `cd /abs/path && git commit ...`; that `cd` only
    affects the command subshell, not the hook process, so a hook that wants the
    real target directory must parse it back out of the command string.

    Handles `cd "x"`, `cd 'x'`, `cd x`, and `cd x && git ...`. Returns the path
    string, or None if there is no leading `cd`.
    """
    match = re.match(r'\s*cd\s+("([^"]*)"|\'([^\']*)\'|([^\s&|;]+))', command)
    if not match:
        return None
    # Whichever capture group matched the quoted or bare path.
    return match.group(2) or match.group(3) or match.group(4)


def resolve_repo_root(directory: str) -> str | None:
    """Resolve a directory to its git repo root via rev-parse --show-toplevel.

    Returns the absolute repo-root path, or None if `directory` is not inside a
    git repository (or git is unavailable).
    """
    try:
        result = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return root or None


def resolve_command_target_dir(command: str) -> str:
    """Resolve the directory a bash command actually targets.

    Parses a leading `cd <path>` from the command (the subshell working dir),
    falling back to the hook process cwd when there is no `cd`. The returned
    path is the candidate directory; callers may further resolve it to a git
    repo root via resolve_repo_root.
    """
    cd_target = extract_cd_target(command)
    if cd_target is None:
        return os.getcwd()
    cd_path = Path(cd_target).expanduser()
    if not cd_path.is_absolute():
        cd_path = Path(os.getcwd()) / cd_path
    return str(cd_path)


def extract_git_command(command: str) -> str | None:
    """Extract the git subcommand from a bash command string.

    Returns the subcommand (commit, push, add, etc.) or None if not a git command.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Malformed shell quoting — fall back to simple split
        tokens = command.split()

    for i, token in enumerate(tokens):
        if token == "git" or token.endswith("/git"):
            # Next non-flag token is the subcommand
            for subsequent in tokens[i + 1:]:
                if not subsequent.startswith("-"):
                    return subsequent
            return None
    return None


def is_protected_branch(branch: str | None = None, cwd: str | None = None) -> bool:
    """Check if the branch is main or master.

    If branch is None, detect the current branch via git, running in `cwd` if
    given (so callers can check the repo the command targets, not the hook
    process cwd).
    """
    if branch is None:
        try:
            cmd = ["git", "branch", "--show-current"]
            if cwd is not None:
                cmd = ["git", "-C", cwd, "branch", "--show-current"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            branch = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
    return branch in ("main", "master")


def extract_file_paths(command: str) -> list[str]:
    """Extract file path arguments from a git add command.

    Filters out flags (arguments starting with -).
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    # Find 'add' after 'git', then collect non-flag args
    found_git = False
    found_add = False
    paths = []
    for token in tokens:
        if not found_git and (token == "git" or token.endswith("/git")):
            found_git = True
            continue
        if found_git and not found_add:
            if token == "add":
                found_add = True
            continue
        if found_add and not token.startswith("-"):
            paths.append(token)
    return paths


def is_broad_add(command: str) -> bool:
    """Detect broad git add commands: git add -A, git add --all, git add ."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    found_git = False
    found_add = False
    for token in tokens:
        if not found_git and (token == "git" or token.endswith("/git")):
            found_git = True
            continue
        if found_git and not found_add:
            if token == "add":
                found_add = True
            continue
        if found_add and token in ("-A", "--all", "."):
            return True
    return False
