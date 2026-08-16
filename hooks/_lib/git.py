"""Git command parsing utilities for Claude Code hooks."""

import os
import re
import shlex
import subprocess
from pathlib import Path


# --- git global-option grammar ---------------------------------------------
#
# A git command is `git [<global-option>...] <subcommand> [<args>...]`, so a
# parser that takes the first non-dash token after `git` mistakes an option
# VALUE for the subcommand: `git -C /abs commit` reads as `/abs`, and the
# commit gate never fires. ~/.claude/command-hygiene.md tells agents to prefer
# `git -C /abs` over `cd`, which makes the option-carrying spelling the house
# style — the default path through these helpers, not an edge case.

# Global options that consume the FOLLOWING token as their value.
GIT_GLOBAL_OPTS_WITH_VALUE = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix", "--config-env",
})

# Global options that stand alone and consume nothing.
GIT_GLOBAL_FLAGS = frozenset({
    "-p", "-P", "--paginate", "--no-pager", "--bare", "--no-replace-objects",
    "--literal-pathspecs", "--no-literal-pathspecs", "--glob-pathspecs",
    "--noglob-pathspecs", "--icase-pathspecs", "--no-optional-locks",
    "--html-path", "--man-path", "--info-path", "--version", "--help",
})

# Tokens that end one command in a shell chain and begin the next.
_SHELL_SEPARATORS = frozenset({"&&", "||", ";", "|", "&"})


def _is_git_token(token: str) -> bool:
    """True iff *token* invokes git itself (`git`, `/usr/bin/git`).

    Deliberately exact: `gitk`, `legit` and `git-foo` are other programs.

    The leading-dash rejection is load-bearing, not tidiness: no binary is
    invoked as `-something`, but an OPTION VALUE can end in `/git`
    (`--git-dir=/abs/repo/git`). Without it that option reads as a second git
    invocation, the option is dropped, and git_global_target_dir answers None —
    sending the safety guard to inspect the wrong repository.
    """
    if token.startswith("-"):
        return False
    return token == "git" or token.endswith("/git")


def _tokenize(command: str) -> list[str]:
    """Split *command* into shell tokens, degrading to a whitespace split.

    Unbalanced quotes make shlex raise ValueError. These parsers run inside a
    hook that blocks closed on an exception, so a malformed command must still
    produce tokens rather than propagate.

    The isinstance check is not decoration: `shlex.split(None)` does not raise,
    it READS STDIN, which would hang the PreToolUse hook and freeze the session.
    """
    if not isinstance(command, str):
        return []
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def _parse_invocations(tokens: list[str]) -> list[dict]:
    """Split *tokens* into one record per git invocation.

    Each record is ``{"globals": [(option, value)], "subcommand": str | None,
    "args": [str]}``. Both git_invocations and git_global_target_dir read these
    records, so the option grammar is written once rather than twice.

    The arg scan ends at a git-looking token as well as at a shell separator,
    because a separator does not always survive tokenisation: shlex renders
    `git add f; git commit -m x` as [..., 'f;', 'git', 'commit', ...], and
    without that stop the trailing commit would be absorbed as an argument and
    escape the gate. The cost is that a positional ARGUMENT ending in /git also
    ends the scan, which over-reports rather than under-reports — the only
    direction a security gate may err.
    """
    records = []
    index = 0
    total = len(tokens)
    while index < total:
        if not _is_git_token(tokens[index]):
            index += 1
            continue
        index += 1

        globals_seen: list[tuple[str, str | None]] = []
        subcommand = None
        while index < total:
            token = tokens[index]
            if token in _SHELL_SEPARATORS or _is_git_token(token):
                break
            if token in GIT_GLOBAL_OPTS_WITH_VALUE:
                # Separate-value form: `-C /abs`, `--work-tree /abs`.
                value = tokens[index + 1] if index + 1 < total else None
                globals_seen.append((token, value))
                index += 2
                continue
            option_name, separator, attached_value = token.partition("=")
            if (
                token.startswith("--")
                and separator
                and option_name in GIT_GLOBAL_OPTS_WITH_VALUE
            ):
                # Attached-value form: `--git-dir=/abs/.git`.
                globals_seen.append((option_name, attached_value))
                index += 1
                continue
            if token in GIT_GLOBAL_FLAGS or token.startswith("-"):
                # An UNRECOGNISED option is skipped as a flag, never as a
                # value-taker. Consuming the next token on a guess could step
                # over the real subcommand and hide a commit from the gate.
                index += 1
                continue
            subcommand = token
            index += 1
            break

        args = []
        while index < total:
            token = tokens[index]
            if token in _SHELL_SEPARATORS or _is_git_token(token):
                break
            args.append(token)
            index += 1

        records.append(
            {"globals": globals_seen, "subcommand": subcommand, "args": args}
        )
    return records


def git_invocations(command: str) -> list[tuple[str, list[str]]]:
    """Return (subcommand, remaining args) for EVERY git invocation in *command*.

    A chain such as `git add f && git -C /abs commit -m x` yields both
    ``('add', ['f'])`` and ``('commit', ['-m', 'x'])``: callers gate on a
    commit anywhere in the chain, not only on the first invocation.

    Never raises — returns [] on any parse failure.
    """
    try:
        return [
            (record["subcommand"], record["args"])
            for record in _parse_invocations(_tokenize(command))
            if record["subcommand"] is not None
        ]
    except Exception:  # noqa: BLE001 — GUARANTEED fail-safe: git-safety-guard imports this module and BLOCKS CLOSED on an uncaught exception, so a parse bug here would deny every Bash call in every session. A specific exception tuple cannot cover an unforeseen input shape (a non-str command reaches shlex as AttributeError, not ValueError); [] degrades to "no git command detected", the only failure mode that keeps the session usable.
        return []


def git_subcommands(command: str) -> set[str]:
    """Return the set of git subcommands invoked anywhere in *command*.

    Never raises — returns an empty set on any parse failure.
    """
    return {subcommand for subcommand, _args in git_invocations(command)}


def has_git_subcommand(command: str, *names: str) -> bool:
    """True iff *command* invokes any of the git subcommands in *names*.

    Never raises — returns False on any parse failure.
    """
    return bool(git_subcommands(command) & set(names))


def git_global_target_dir(command: str) -> str | None:
    """Return the directory a git global option targets, or None if there is none.

    Precedence: the first `-C`, else the first `--work-tree`, else the first
    `--git-dir` (whose trailing `.git` segment is stripped to give the worktree
    root). Both the `-C <path>` and `--git-dir=<path>` spellings are handled.

    When a chain carries two different targets the FIRST wins; reconciling
    divergent targets across a compound is TRK-137 territory, not this helper's.

    Never raises — returns None on any parse failure.
    """
    try:
        records = _parse_invocations(_tokenize(command))
        seen = [pair for record in records for pair in record["globals"]]
        for option in ("-C", "--work-tree", "--git-dir"):
            for option_name, value in seen:
                if option_name != option or not value:
                    continue
                if option == "--git-dir":
                    git_dir = Path(value)
                    return str(git_dir.parent) if git_dir.name == ".git" else value
                return value
        return None
    except Exception:  # noqa: BLE001 — GUARANTEED fail-safe, same contract as git_invocations: this module is imported by a hook that blocks closed on an uncaught exception. None degrades to "no global target", which returns callers to the pre-existing cd/cwd answer.
        return None


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

    A leading `cd <path>` sets the base directory (the command runs in a
    subshell, so that `cd` never reaches the hook process); a git global option
    such as `-C` then applies RELATIVE TO THAT BASE. With neither, the base is
    the hook process cwd. The result is a candidate directory; callers may
    further resolve it to a git repo root via resolve_repo_root.

    Never raises — any failure in the git-option step degrades to the plain
    `cd`/cwd answer this function returned before `-C` was understood.
    """
    cd_target = extract_cd_target(command)
    if cd_target is None:
        base_path = Path(os.getcwd())
    else:
        base_path = Path(cd_target).expanduser()
        if not base_path.is_absolute():
            base_path = Path(os.getcwd()) / base_path

    try:
        global_dir = git_global_target_dir(command)
        if global_dir is None:
            return str(base_path)
        global_path = Path(global_dir).expanduser()
        if not global_path.is_absolute():
            global_path = base_path / global_path
        return str(global_path)
    except (OSError, RuntimeError, ValueError):
        # Path() rejects NUL bytes and expanduser() fails with no resolvable
        # home; either way, fall back to the pre-existing cd/cwd result.
        return str(base_path)


def extract_git_command(command: str) -> str | None:
    """Extract the FIRST git subcommand from a bash command string.

    Returns the subcommand (commit, push, add, etc.) or None if the command
    invokes no git subcommand. Global options are skipped, so
    `git -C /abs commit` yields `commit` rather than `/abs`.
    """
    invocations = git_invocations(command)
    return invocations[0][0] if invocations else None


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
