"""Git command parsing utilities for Claude Code hooks."""

import shlex
import subprocess


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


def is_protected_branch(branch: str | None = None) -> bool:
    """Check if the branch is main or master.

    If branch is None, detect the current branch via git.
    """
    if branch is None:
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=3
            )
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
