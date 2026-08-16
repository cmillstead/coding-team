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

# Shell keywords / grouping tokens that open a new simple-command position, so a
# `git` token immediately after one is a real invocation (`do git push`,
# `then git commit`, `{ git commit; }`, `( git commit )`, `! git commit`).
_HEAD_STARTERS = frozenset({"do", "then", "else", "{", "(", "!"})

# Command wrappers that exec their trailing argv as a new command, so the `git`
# token that follows one (possibly past assignments/options) still runs git
# (`sudo git push`, `time git commit`, `xargs git commit`, `sudo -u bob git
# commit`, `nice -n 10 git commit`). Deliberately a closed allowlist: an unknown
# wrapper is NOT assumed to exec git. A git token past a wrapper's OWN options is
# recognised via the SEGMENT-HEAD clause in _git_token_is_head — the segment head
# being a wrapper is what separates `sudo -u bob git commit` (git is real) from
# `grep -e git commit` (git is an argument); the immediate predecessor is a
# dash-option in both and cannot tell them apart.
_EXEC_WRAPPERS = frozenset({
    "env", "sudo", "time", "command", "exec", "nohup",
    "nice", "ionice", "stdbuf", "xargs", "timeout", "builtin",
})

# Leading `NAME=value` environment assignment, e.g. `FOO=1 git commit`.
_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")

# Shell builtins/commands that change the process working directory.
_DIR_CHANGE_COMMANDS = frozenset({"cd", "pushd", "popd", "chdir"})

# Wrappers that can carry a directory-change OPTION (--chdir / -C) before their
# argv, e.g. `env --chdir=/B git commit`. Detected separately from a plain `cd`
# because the safety guard can never confirm which directory they land in.
_CHDIR_WRAPPERS = frozenset({"env", "command"})


def _git_token_is_head(prev: str | None, segment_head: str | None = None) -> bool:
    """True iff a git token preceded by *prev* is in command-head position.

    Over-detects on ambiguity (security-safe): only DEMOTES a git token to an
    argument when the preceding token is a plain command/argument word
    (`echo git commit`, `grep git commit f`). Every ambiguous predecessor is
    treated as head so a real git invocation still reaches the gates.

    A git token is head-position iff EITHER a boundary condition on *prev* holds
    (start-of-segment, a separator, a glued separator, a head-starter keyword, an
    exec-wrapper, a `VAR=val` assignment, or git-after-git), OR *segment_head* —
    the command word that starts this pipeline/compound segment — is a known
    exec-wrapper. The segment-head clause is the distinguishing fact: `sudo -u bob
    git commit`, `nice -n 10 git commit` and `env --chdir=/B git commit` all run a
    REAL git past the wrapper's OWN options, while `grep -e git commit f` has git
    sitting in a text tool's argument list. The immediate predecessor is a
    dash-option (`-e`, `--chdir=/B`) or an option value (`bob`, `10`) in BOTH, so
    it cannot tell them apart — the segment head can (`sudo`/`nice`/`env` are
    wrappers, `grep` is not).
    """
    if prev is None:
        return True
    if prev in _SHELL_SEPARATORS:
        return True
    if prev and prev[-1] in ";&|":
        # Glued separator that survived tokenisation: `git add f; git commit`
        # renders as [..., 'f;', 'git', ...], so the ';' rides on the prev token.
        return True
    if prev in _HEAD_STARTERS:
        return True
    if prev in _EXEC_WRAPPERS:
        return True
    if _ASSIGN_RE.match(prev):
        return True
    if _is_git_token(prev):
        # Defensive: `git ... git commit` without a separator (unusual) — still
        # treat the second git as head so its subcommand is seen.
        return True
    if segment_head is not None and segment_head in _EXEC_WRAPPERS:
        # The command that starts this segment execs its trailing argv, so a git
        # token past the wrapper's own options/assignments is a REAL invocation
        # (`sudo -u bob git commit`, `nice -n 10 git commit`). This is what a
        # blunt `prev.startswith("-")` clause could not do without also
        # false-matching `grep -e git commit` (segment head `grep`, git is an
        # argument) — a TRK-048 regression.
        return True
    return False


def _segment_heads(tokens: list[str]) -> list[str | None]:
    """Return, per token position, the command word that starts its shell segment.

    The segment head is the FIRST non-assignment token after the most recent
    shell separator (start-of-command counts as a separator); leading `VAR=val`
    assignment tokens are skipped, so `FOO=1 sudo git commit` has head `sudo`.
    _parse_invocations uses this to tell a git token run past a wrapper's own
    options (a real invocation) from a git token in a text tool's argument list.
    """
    heads: list[str | None] = []
    current_head: str | None = None
    awaiting_head = True
    for token in tokens:
        if awaiting_head and not _ASSIGN_RE.match(token):
            current_head = token
            awaiting_head = False
        heads.append(current_head)
        if token in _SHELL_SEPARATORS or (token and token[-1] in ";&|"):
            # A separator (or a glued `f;`) ends this segment; the next token
            # starts a fresh one whose head we have not seen yet.
            current_head = None
            awaiting_head = True
    return heads


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


# Shell separator characters that combine into `;`, `|`, `&`, `&&`, `||`. A run
# of these outside quotes is a statement boundary that shlex leaves GLUED to an
# adjacent word when no whitespace surrounds it.
_GLUED_SEP_CHARS = frozenset(";|&")

# Closing grouping tokens. shlex glues a trailing `)`/`}` onto the preceding word
# (`git commit)` -> subcommand 'commit)'), which HIDES the subcommand from the
# gates. Splitting the CLOSING grouper surfaces the subcommand so it is detected;
# the OPENING `(`/`{`/`$(` is deliberately NOT split, so a `$(git ...)` command
# substitution stays glued as `$(git` and is not mistaken for a real invocation
# (the TRK-048 head-anchoring contract).
_CLOSING_GROUP_CHARS = frozenset(")}")


def _split_glued_separators(command: str) -> str:
    """Insert whitespace around UNQUOTED shell separators/closing groupers.

    shlex leaves a separator glued to an adjacent word when no whitespace
    surrounds it (`git add f&&git commit` -> ['add', 'f&&git', 'commit'],
    `git commit; echo` -> ['commit;', 'echo'], `(cd /r && git commit)` ->
    [..., 'commit)']), which hides the second command from the git parser and the
    cd-path resolver. This pass rewrites such runs of `;`, `|`, `&` (covering
    `;`, `|`, `&`, `&&`, `||`) and each closing `)`/`}` with surrounding
    whitespace, so `shlex.split` then yields them as standalone tokens.

    Quote- and escape-aware: a separator inside single/double quotes (or one that
    is backslash-escaped) is left untouched, so a quoted commit message such as
    -m "a;b && c" keeps its `;`/`&&` as literal message text, not a split, and a
    conventional-commit scope like -m "fix(x): y" keeps its parens intact.

    Never raises: returns the original command on any unexpected input, so the
    hook that imports this module cannot be block-closed by a tokeniser bug.
    """
    try:
        if not isinstance(command, str):
            return command
        out: list[str] = []
        in_single = False
        in_double = False
        index = 0
        length = len(command)
        while index < length:
            char = command[index]
            if in_single:
                out.append(char)
                if char == "'":
                    in_single = False
                index += 1
                continue
            if in_double:
                if char == "\\" and index + 1 < length:
                    out.append(char)
                    out.append(command[index + 1])
                    index += 2
                    continue
                out.append(char)
                if char == '"':
                    in_double = False
                index += 1
                continue
            # Unquoted (normal) state.
            if char == "\\" and index + 1 < length:
                # Escaped char — emit both verbatim so an escaped `;`/`&` is not
                # treated as a separator and a shlex escape (`c\d`) is preserved.
                out.append(char)
                out.append(command[index + 1])
                index += 2
                continue
            if char == "'":
                in_single = True
                out.append(char)
                index += 1
                continue
            if char == '"':
                in_double = True
                out.append(char)
                index += 1
                continue
            if char in _GLUED_SEP_CHARS:
                run_end = index
                while run_end < length and command[run_end] in _GLUED_SEP_CHARS:
                    run_end += 1
                out.append(" ")
                out.append(command[index:run_end])
                out.append(" ")
                index = run_end
                continue
            if char in _CLOSING_GROUP_CHARS:
                out.append(" ")
                out.append(char)
                out.append(" ")
                index += 1
                continue
            out.append(char)
            index += 1
        return "".join(out)
    except Exception:  # noqa: BLE001 — tokeniser fail-safe: this module is imported by a hook that blocks closed on an uncaught exception. Returning the raw command degrades to the pre-existing (glued) tokenisation, never a crash.
        return command


def _tokenize(command: str) -> list[str]:
    """Split *command* into shell tokens, degrading to a whitespace split.

    Unbalanced quotes make shlex raise ValueError. These parsers run inside a
    hook that blocks closed on an exception, so a malformed command must still
    produce tokens rather than propagate.

    Glued shell separators (`f&&git`, `commit;`) and closing groupers (`commit)`)
    are normalised via _split_glued_separators FIRST — quote-aware, so a
    separator inside a quoted message is left intact — so the downstream head
    anchoring, subcommand matching and cd-path resolution all see clean tokens.

    The isinstance check is not decoration: `shlex.split(None)` does not raise,
    it READS STDIN, which would hang the PreToolUse hook and freeze the session.
    """
    if not isinstance(command, str):
        return []
    normalized = _split_glued_separators(command)
    try:
        return shlex.split(normalized)
    except ValueError:
        return normalized.split()


def _parse_invocations(tokens: list[str]) -> list[dict]:
    """Split *tokens* into one record per git invocation.

    Each record is ``{"globals": [(option, value)], "subcommand": str | None,
    "args": [str]}``. Both git_invocations and git_global_target_dir read these
    records, so the option grammar is written once rather than twice.

    A `git` token only starts a record when it is in command-HEAD position
    (see _git_token_is_head): a git token in argument position — `echo git
    commit`, `grep git commit f`, `ls # git commit` — is skipped, so a textual
    mention of a git command never trips the gates (TRK-048 / TRK-139).

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
    heads = _segment_heads(tokens)
    while index < total:
        if not _is_git_token(tokens[index]):
            index += 1
            continue
        prev = tokens[index - 1] if index > 0 else None
        if not _git_token_is_head(prev, heads[index]):
            # A git token in argument position (`echo git commit`, `grep git
            # commit f`, `grep -e git commit f`, `ls # git commit`) is NOT an
            # invocation — skip it so the gates never fire on a mere textual
            # mention (TRK-048 / TRK-139). The segment head (`grep`/`echo`) is
            # not an exec-wrapper, so the dash-option predecessor `-e` does not
            # promote git to head.
            index += 1
            continue
        head_index = index  # token position of this invocation's `git` (TRK-139 Fix C)
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
            {"globals": globals_seen, "subcommand": subcommand, "args": args,
             "head_index": head_index}
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


def _carries_chdir_option(token: str) -> bool:
    """True iff *token* is a directory-change option (`--chdir[=...]` / `-C`)."""
    return token == "--chdir" or token.startswith("--chdir=") or token == "-C"


def _find_dir_change_ops(tokens: list[str]) -> list[dict]:
    """Return one record per directory-change op in *tokens*.

    A record is ``{"kind": str, "path": str | None, "leading": bool,
    "index": int}``. The kinds are the plain builtins (`cd`/`pushd`/`popd`/
    `chdir`) and ``"wrapper-chdir"`` for an env/command wrapper carrying
    `--chdir`/`-C`. ``index`` is the op's token position, which
    resolve_branch_check_target uses to ignore a dir-change that lands AFTER the
    last gated git op (TRK-139 Fix C). Only HEAD-position tokens are considered
    (reusing _git_token_is_head's boundary logic), so a directory name that
    merely appears as an argument is not mistaken for a `cd`.
    """
    ops: list[dict] = []
    total = len(tokens)
    for index, token in enumerate(tokens):
        prev = tokens[index - 1] if index > 0 else None
        if not _git_token_is_head(prev):
            continue
        if token in _DIR_CHANGE_COMMANDS:
            path = None
            if index + 1 < total:
                nxt = tokens[index + 1]
                if nxt not in _SHELL_SEPARATORS and not (nxt and nxt[-1] in ";&|"):
                    path = nxt
            ops.append({"kind": token, "path": path, "leading": index == 0,
                        "index": index})
        elif token in _CHDIR_WRAPPERS:
            # Scan the wrapper's own tokens (assignments/options) up to its wrapped
            # command or the next separator; a --chdir/-C among them is a chdir op.
            scan = index + 1
            while scan < total:
                inner = tokens[scan]
                if inner in _SHELL_SEPARATORS or (inner and inner[-1] in ";&|"):
                    break
                if _carries_chdir_option(inner):
                    ops.append({"kind": "wrapper-chdir", "path": None,
                                "leading": index == 0, "index": index})
                    break
                if not inner.startswith("-") and not _ASSIGN_RE.match(inner):
                    break  # reached the wrapped command word
                scan += 1
    return ops


def _is_clean_absolute(path: str) -> bool:
    """True iff *path* is absolute and free of a NUL byte (safe to shell out)."""
    if "\x00" in path:
        return False
    return Path(path).is_absolute()


def _apply_relative_global(base: str, global_dir: str | None) -> str:
    """Apply a RELATIVE global target to *base*, or return *base* if there is none.

    An absolute global_dir is returned as-is (defensive; rule 1 handles absolute
    globals before this is reached).
    """
    if global_dir is None:
        return base
    global_path = Path(global_dir)
    if global_path.is_absolute():
        return str(global_path)
    return str(Path(base) / global_path)


def _resolve_or_candidate(directory: str) -> str:
    """Canonicalise *directory* and resolve it to its git repo root, else return it.

    ``Path.resolve()`` runs BEFORE resolve_repo_root shells out, so an embedded
    NUL (ValueError) or a symlink loop (RuntimeError/OSError) is raised here and
    caught by resolve_branch_check_target's except clause rather than reaching
    subprocess, which does not catch a NUL in argv. A directory that is not inside
    a git repo is a concrete, unambiguous target — returned unchanged so the
    branch check runs against it directly.
    """
    canonical = str(Path(directory).resolve())
    root = resolve_repo_root(canonical)
    return root if root is not None else canonical


# Shell grouping / substitution characters. Their presence OUTSIDE quotes means
# the commit/push/merge can run in a subshell or a substitution whose cwd the
# safety guard can never confirm, so the branch gate must fail-safe block.
# `$(` is covered by `(`; `${...}` by `{`.
_GROUPING_SUBSTITUTION_CHARS = frozenset("(){}`")


def _has_unquoted_grouping_or_substitution(command: str) -> bool:
    """True iff *command* has a shell grouping/substitution char OUTSIDE quotes.

    Flags `(`, `)`, `{`, `}` and a backtick (so subshells `( ... )`, brace groups
    `{ ...; }`, command substitutions `$( ... )` / backticks, and `${...}`
    expansions all trip). This is the fail-safe trigger for resolve_branch_check_
    target: any such construct means the commit's cwd/repo is unknowable.

    QUOTE-AWARE by design, via a char-by-char state machine that tracks single-
    and double-quote spans and backslash escapes. This is the whole point: a
    conventional-commit message such as -m "fix(parser): tidy (again)" has
    literal parens INSIDE quotes and must NOT be flagged. A naive substring scan
    (`"(" in command`) would false-block every scoped conventional-commit
    message, which is why compound_allow.is_multi_statement (a broader,
    quote-stripping detector) is NOT reused here.

    Never raises: returns False on any unexpected input. A pathological input
    that somehow escapes this scan still reaches resolve_branch_check_target's
    own try/except, which fails safe to (None, True).
    """
    try:
        if not isinstance(command, str):
            return False
        in_single = False
        in_double = False
        index = 0
        length = len(command)
        while index < length:
            char = command[index]
            if in_single:
                if char == "'":
                    in_single = False
                index += 1
                continue
            if in_double:
                if char == "\\" and index + 1 < length:
                    index += 2
                    continue
                if char == '"':
                    in_double = False
                index += 1
                continue
            # Unquoted (normal) state.
            if char == "\\" and index + 1 < length:
                index += 2
                continue
            if char == "'":
                in_single = True
            elif char == '"':
                in_double = True
            elif char in _GROUPING_SUBSTITUTION_CHARS:
                return True
            index += 1
        return False
    except Exception:  # noqa: BLE001 — fail-safe: a scan bug degrades to "no grouping detected"; the downstream resolver rules are themselves fail-safe on ambiguity.
        return False


def resolve_branch_check_target(command: str) -> tuple[str | None, bool]:
    """Return (repo_root_or_candidate, ambiguous) for the branch gate. NEVER raises.

    ``ambiguous=True`` (paired with a None target) tells the caller to fail-safe
    block: the safety guard cannot confirm which repo/branch a commit/push/merge
    in *command* targets. Clean resolution is a WHITELIST of three shapes, checked
    in order; every other shape is ambiguous.

    1. An ABSOLUTE git global target (`git -C /abs`, `--git-dir=/abs/.git`, ...)
       is cwd-independent and dominates any cd/pushd — target = that path.
    2. NO directory-change op present — base = the hook process cwd; a relative
       global target applies to it.
    3. EXACTLY ONE directory-change op, a LEADING `cd` with an ABSOLUTE path —
       base = that path; a relative global target applies to it. (Multiple git
       invocations in the chain do NOT make the cwd ambiguous.)

    Ambiguous otherwise: >1 dir-change op; a non-leading `cd`; any
    pushd/popd/chdir; an env/command wrapper carrying --chdir/-C; a single
    relative `cd`.

    Fail direction is ambiguous → block: the whole body is wrapped so any
    OSError/ValueError/RuntimeError (Path() raises ValueError on an embedded NUL,
    RuntimeError on a symlink-loop resolve()) returns (None, True) rather than
    propagating to git-safety-guard's block-closed top-level handler.
    """
    try:
        # Fix A (TRK-137 class): an UNQUOTED shell grouping/substitution
        # construct — a subshell `( ... )`, a brace group `{ ...; }`, a command
        # substitution `$( ... )` / backticks, or a `${...}` expansion — means the
        # commit can run in a subshell whose cwd shlex cannot expose to
        # _find_dir_change_ops. Fail-safe block BEFORE the clean-resolution rules;
        # quote-aware so a scoped conventional-commit message keeps resolving.
        if _has_unquoted_grouping_or_substitution(command):
            return (None, True)

        tokens = _tokenize(command)
        ops = _find_dir_change_ops(tokens)
        global_dir = git_global_target_dir(command)

        # Fix C (TRK-139 own regression): a dir-change op positioned AFTER the
        # last gated git op (commit/push/merge) cannot affect that op's cwd, so it
        # does not contribute to ambiguity. `git commit && cd /tmp` resolves the
        # cwd cleanly; `cd /A && cd /B && git commit` (both cds precede the
        # commit) stays ambiguous.
        records = _parse_invocations(tokens)
        gated_indices = [
            record["head_index"] for record in records
            if record.get("subcommand") in ("commit", "push", "merge")
        ]
        if gated_indices:
            last_gated_index = max(gated_indices)
            ops = [op for op in ops if op["index"] < last_gated_index]

        # Rule 1: an absolute global target dominates any cd/pushd.
        if global_dir is not None and _is_clean_absolute(global_dir):
            return (_resolve_or_candidate(global_dir), False)

        if not ops:
            # Rule 2: base = process cwd; a relative global target applies to it.
            candidate = _apply_relative_global(os.getcwd(), global_dir)
            return (_resolve_or_candidate(candidate), False)

        # At least one directory-change op is present.
        if len(ops) != 1:
            return (None, True)  # >1 chdir op — cannot confirm the landing dir
        op = ops[0]
        if op["kind"] != "cd" or not op["leading"]:
            return (None, True)  # pushd/popd/chdir/wrapper-chdir, or a non-leading cd
        cd_path = op["path"]
        if cd_path is None or not _is_clean_absolute(cd_path):
            return (None, True)  # a relative (or missing) cd target is ambiguous
        # Rule 3: single leading absolute cd; a relative global target applies to it.
        candidate = _apply_relative_global(cd_path, global_dir)
        return (_resolve_or_candidate(candidate), False)
    except (OSError, ValueError, RuntimeError):
        return (None, True)


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
