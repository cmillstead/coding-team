#!/usr/bin/env python3
"""Claude Code Pre+PostToolUse hook: consolidated git safety guard.

Combines secret-guard, branch-guard, and pre-completion-checklist into a single
hook with deterministic execution order:

PreToolUse on Bash:
  1. Secret check — block git add of secret files or broad adds
  2. Branch check — block commit/push/merge on main/master
  3. Verification checklist — require test+lint PASSED before commit/push
  Track verification commands for checklist state.

PostToolUse on Bash:
  Capture exit codes from verification commands (lint, test, typecheck).
  Used by the PreToolUse commit gate to verify tests/lint actually PASSED,
  not just that they were run.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

import glob
import re
import subprocess
import time
from pathlib import Path

from _lib import event, git, state, output

# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------
SECRET_NAMES = {".env", ".env.local", ".env.production", ".env.staging", ".env.development"}
SECRET_SUFFIXES = {".key", ".pem", ".secret", ".p12", ".pfx", ".jks", ".keystore"}
SECRET_PREFIXES = {"credentials", "secret", "serviceaccount"}

# ---------------------------------------------------------------------------
# Verification tracking
# ---------------------------------------------------------------------------
STALE_SECONDS = 7200  # 2 hours

VERIFICATION_PATTERNS = [
    r'\bnpm\s+test\b',
    r'\bnpm\s+run\s+test\b',
    r'\bnpx\s+jest\b',
    r'\bnpx\s+vitest\b',
    r'\bnpx\s+pytest\b',
    r'\bpytest\b',
    r'\bcargo\s+test\b',
    r'\bgo\s+test\b',
    r'\bnpm\s+run\s+lint\b',
    r'\bnpx\s+eslint\b',
    r'\bnpx\s+tsc\s+--noEmit\b',
    r'\btsc\s+--noEmit\b',
    r'\bmypy\b',
    r'\bruff\s+check\b',
    r'\bcargo\s+clippy\b',
    r'\bmake\s+test\b',
    r'\bmake\s+lint\b',
    r'\bmake\s+check\b',
    r'\bbash\s+-n\b',
    r'\bshellcheck\b',
]

COMMIT_PREFIXES = ["feat:", "fix:", "test:", "docs:", "refactor:", "chore:"]

PROJECT_MARKERS = [
    "package.json", "tsconfig.json", "deno.json",
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "Pipfile", "tox.ini",
    "Cargo.toml",
    "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts", "build.sbt",
    "Directory.Build.props",
    "Gemfile", "Rakefile",
    "composer.json",
    "Package.swift",
    "pubspec.yaml",
    "mix.exs",
    "stack.yaml", "cabal.project",
    "CMakeLists.txt", "meson.build", "configure.ac",
    "build.zig",
    "deps.edn", "project.clj",
    "Project.toml",
    "Makefile", "Justfile",
]

GLOB_MARKERS = ["*.csproj", "*.sln", "*.xcodeproj", "*.nimble"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_secret_file(filepath: str) -> str | None:
    """Check if a filepath matches secret patterns. Returns reason or None."""
    path = Path(filepath)
    if path.name in SECRET_NAMES:
        return f"secret filename '{path.name}'"
    if path.suffix in SECRET_SUFFIXES:
        return f"secret extension '{path.suffix}'"
    if path.stem.lower() in SECRET_PREFIXES:
        return f"secret prefix '{path.stem}'"
    if path.stem.lower() == "credentials":
        return f"credentials file '{path.name}'"
    return None


def is_verification(command: str) -> bool:
    return any(re.search(p, command) for p in VERIFICATION_PATTERNS)


def is_commit_or_push(command: str) -> bool:
    return bool(re.search(r'\bgit\s+(commit|push)\b', command))


def is_commit_push_or_merge(command: str) -> bool:
    """Return True if the command contains a git commit, push, or merge anywhere.

    Uses a regex scan rather than first-subcommand detection so that chained
    commands like `git add f && git commit -m x` are not misclassified by
    first-subcommand extraction (which would return 'add' and skip the branch
    check entirely).
    """
    return bool(re.search(r'\bgit\s+(commit|push|merge)\b', command))


def is_delete_only_push(command: str) -> bool:
    """Return True iff command is a push that deletes remote branches and nothing else.

    Two supported forms:
    - Flag form:   git push [opts] --delete|-d <remote> <branch>...
    - Colon form:  git push [opts] <remote> :<ref>... (every refspec starts with ':')

    Mixed pushes (some refspecs are deletions, some are normal) return False so
    the safety guards still apply. On any parsing uncertainty, returns False
    (fail-safe: guards stay ON).
    """
    # Must contain a git push; anything else is immediately False.
    if not re.search(r'\bgit\s+push\b', command):
        return False

    # --- Flag form: --delete or -d is present ---
    # We only need to confirm the push has the flag; the branches are positional
    # arguments after the remote so there is nothing unsafe about exempting this.
    if re.search(r'\bgit\s+push\b.*?(?:--delete|-d)\b', command, re.DOTALL):
        return True

    # --- Colon form: every non-flag, non-remote argument starts with ':' ---
    # Isolate the git push invocation from any leading shell fragment (e.g. "cd /x && ").
    push_match = re.search(r'\bgit\s+push\b(.*)', command)
    if not push_match:
        return False

    push_args_str = push_match.group(1)

    # Tokenize safely: shlex handles quoting but may raise on unbalanced shell syntax.
    import shlex
    try:
        tokens = shlex.split(push_args_str)
    except ValueError:
        try:
            tokens = push_args_str.split()
        except Exception:
            return False  # Cannot parse — fail safe

    # Walk the token list: skip flags (start with '-'), consume the remote name
    # (first non-flag), then collect refspecs.
    saw_remote = False
    refspecs: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-"):
            # Flags that take a value: consume the next token too.
            # Known value-taking push flags: --repo, --push-option/-o, --recurse-submodules
            if tok in ("--repo", "--push-option", "-o", "--recurse-submodules"):
                i += 2
                continue
            # --flag=value style: nothing extra to consume
            i += 1
            continue
        if not saw_remote:
            saw_remote = True
            i += 1
            continue
        refspecs.append(tok)
        i += 1

    # Must have at least one refspec and ALL must start with ':'.
    if not refspecs:
        return False
    return all(r.startswith(":") for r in refspecs)


def extract_commit_message(command: str) -> str | None:
    """Extract commit message from git commit command.

    Handles -m "msg", -m 'msg', -F file, --file=file, and HEREDOC patterns.
    Returns None if the message cannot be extracted.
    """
    # Check for HEREDOC pattern: -m "$(cat <<'EOF'\n...\nEOF\n)"
    heredoc_match = re.search(
        r"-m\s+\"\$\(cat\s+<<'?(\w+)'?\s*\n(.*?)\n\1\s*\)\"",
        command, re.DOTALL
    )
    if heredoc_match:
        return heredoc_match.group(2).strip()

    # Check -F / --file= (read the file contents)
    file_patterns = [
        re.compile(r'-F\s+"([^"]*)"'),
        re.compile(r"-F\s+'([^']*)'"),
        re.compile(r'-F\s+(\S+)'),
        re.compile(r'--file="([^"]*)"'),
        re.compile(r"--file='([^']*)'"),
        re.compile(r'--file=(\S+)'),
    ]
    for pattern in file_patterns:
        match = pattern.search(command)
        if match:
            filepath = match.group(1)
            try:
                with open(filepath) as f:
                    return f.read().strip()
            except (OSError, IOError):
                return None  # Can't read file = can't validate

    # Existing -m patterns
    patterns = [
        re.compile(r'-m\s+"([^"]*)"'),
        re.compile(r"-m\s+'([^']*)'"),
        re.compile(r'-m\s+(\S+)'),
    ]
    for pattern in patterns:
        match = pattern.search(command)
        if match:
            return match.group(1)
    return None


def _package_json_has_verification_script(path: str) -> bool:
    """Return True iff a package.json declares a runnable test/lint/typecheck script.

    Fail-safe: returns True (assume verification IS required) on any read/parse
    error — better to over-require verification than to silently exempt a repo
    that may have test infrastructure we cannot inspect.
    """
    import json as _json

    VERIFY_SCRIPT_KEYS = (
        "test", "lint", "typecheck", "type-check", "check",
        "tsc", "eslint", "vitest", "jest",
    )
    try:
        with open(path) as fh:
            data = _json.load(fh)
        scripts = data.get("scripts", {})
        if not isinstance(scripts, dict):
            return False
        keys = [k.lower() for k in scripts.keys()]
        return any(any(vk in k for vk in VERIFY_SCRIPT_KEYS) for k in keys)
    except (OSError, ValueError):
        return True  # fail-safe: cannot read → assume verification required


def has_project_infrastructure(root: str | None = None) -> bool:
    """Check if a repo root has build/test infrastructure (not docs-only).

    A script-less package.json (one with no test/lint/typecheck keys in
    ``scripts``) is explicitly excluded: it provides no runnable verification
    command and would make the checklist permanently un-satisfiable.  All
    other PROJECT_MARKERS are accepted unconditionally.

    Args:
        root: Directory to inspect for project markers. Defaults to
            os.getcwd() to preserve legacy call sites.
    """
    if root is None:
        root = os.getcwd()
    for m in PROJECT_MARKERS:
        marker_path = os.path.join(root, m)
        if not os.path.exists(marker_path):
            continue
        if m == "package.json" and not _package_json_has_verification_script(marker_path):
            continue  # script-less package.json provides no runnable verification
        return True
    return any(glob.glob(os.path.join(root, g)) for g in GLOB_MARKERS)


def resolve_commit_target_root(command: str) -> str:
    """Resolve the repo root the commit actually targets.

    Parses a leading `cd <path>` from the command (the harness runs commits as
    `cd /abs/path && git commit ...`, and that `cd` does NOT affect the hook
    process cwd), then resolves that directory to its git repo root. Falls back
    to the candidate directory itself when it is not inside a git repo, which
    keeps the docs-only check fail-safe: an unresolvable code dir with markers
    still requires verification.
    """
    target_dir = git.resolve_command_target_dir(command)
    repo_root = git.resolve_repo_root(target_dir)
    return repo_root if repo_root is not None else target_dir


# Documentation file extensions that are safe to commit without test/lint checks.
_DOCS_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc"}


def is_pointer_only_commit(command: str, target_root: str) -> bool:
    """Return True iff command is a git commit and every staged entry is a submodule pointer.

    A submodule pointer (gitlink) has mode 160000 in the destination-mode field of
    ``git diff --cached --raw`` output. The raw format per entry is::

        :<old-mode> <new-mode> <old-sha> <new-sha> <status>\\t<path>

    The destination mode (new-mode) is the second space-separated field on the
    colon-prefixed metadata line. An entry is a gitlink when that field equals
    ``160000``.

    Fail-safe: returns False on any subprocess error, timeout, empty staged list,
    non-commit command, or mixed staged content. Never raises.

    Args:
        command:     The full bash command string (e.g. "cd /repo && git commit -m ...").
        target_root: The repo root to inspect for staged entries.
    """
    # Only exempt git commit — pushes are out of scope.
    if not re.search(r'\bgit\s+commit\b', command):
        return False

    try:
        result = subprocess.run(
            ["git", "-C", target_root, "diff", "--cached", "--raw"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError, ValueError):
        return False

    # Fail-safe: nothing staged → cannot confirm pointer-only → apply checklist.
    if not lines:
        return False

    for line in lines:
        # Each raw-format metadata line starts with ':'.
        if not line.startswith(":"):
            return False
        # Format: :<old-mode> <new-mode> <old-sha> <new-sha> <status>\t<path>
        # The destination mode is the 2nd whitespace-separated field.
        try:
            parts = line[1:].split()  # strip leading ':'
            dest_mode = parts[1]
        except (IndexError, ValueError):
            return False
        if dest_mode != "160000":
            return False

    return True


def is_docs_only_commit(command: str, target_root: str) -> bool:
    """Return True iff command is a git commit and every staged file is documentation.

    Fail-safe: returns False on any subprocess error, timeout, empty staged list,
    non-commit command, or mixed code+docs staging. Never raises.

    Args:
        command:     The full bash command string (e.g. "cd /repo && git commit -m ...").
        target_root: The repo root to inspect for staged files.
    """
    # Only exempt git commit — pushes are out of scope.
    if not re.search(r'\bgit\s+commit\b', command):
        return False

    try:
        result = subprocess.run(
            ["git", "-C", target_root, "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        staged_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, OSError, ValueError):
        return False

    # Fail-safe: nothing staged → cannot confirm docs-only → apply checklist.
    if not staged_files:
        return False

    return all(
        Path(f).suffix.lower() in _DOCS_EXTENSIONS
        for f in staged_files
    )



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _extract_exit_code(tool_result) -> int | None:
    """Extract exit code from Bash tool_result."""
    if isinstance(tool_result, dict):
        # CC provides exit_code in structured result
        if "exit_code" in tool_result:
            return int(tool_result["exit_code"])
        # Fallback: check stdout for common exit code patterns (not reliably parseable)
        pass
    elif isinstance(tool_result, str):
        pass
    else:
        return None
    # If the tool_result is from a failed command, CC typically wraps it
    # in an error block — we can't reliably extract exit code from text
    return None


def _handle_post_tool_use(ev: dict) -> None:
    """PostToolUse: capture exit codes from verification commands."""
    command = event.get_command(ev)
    if not command or not is_verification(command):
        return

    tool_result = ev.get("tool_result", "")
    exit_code = _extract_exit_code(tool_result)

    # Heuristic: if tool_result contains "error" or "Error" lines indicative
    # of lint/test failures, treat as non-zero even without explicit exit code.
    # CC Bash tool sets exit_code in the result dict when available.
    if exit_code is None and isinstance(tool_result, str):
        # Check if the output was from a command that CC reported as failed
        # CC wraps failed commands with "Exit code: N" in some contexts
        import re as _re
        m = _re.search(r'Exit code:\s*(\d+)', tool_result)
        if m:
            exit_code = int(m.group(1))

    state_file = state.get_state_file("claude-verification")
    st = state.load_state(state_file, {"verifications": [], "last_updated": time.time()})
    if state.is_stale(st):
        st = {"verifications": [], "last_updated": time.time()}
    st["verifications"].append({
        "command": command,
        "time": time.time(),
        "exit_code": exit_code,
    })
    st["verifications"] = st["verifications"][-20:]
    state.save_state(state_file, st)


def main():
    ev = event.parse_event()
    if not ev:
        return

    tool_name = event.get_tool_name(ev)
    if tool_name != "Bash":
        return

    # PostToolUse: capture exit codes from verification commands
    if "tool_result" in ev:
        _handle_post_tool_use(ev)
        return

    command = event.get_command(ev)
    if not command:
        return

    git_subcmd = git.extract_git_command(command)

    # --- Track verification commands in PreToolUse too (fallback if PostToolUse misses) ---
    if is_verification(command):
        state_file = state.get_state_file("claude-verification")
        st = state.load_state(state_file, {"verifications": [], "last_updated": time.time()})
        if state.is_stale(st):
            st = {"verifications": [], "last_updated": time.time()}
        # Only add if not already tracked by PostToolUse (check last entry)
        recent = st.get("verifications", [])
        already_tracked = (
            recent and recent[-1].get("command") == command
            and time.time() - recent[-1]["time"] < 5
        )
        if not already_tracked:
            st["verifications"].append({
                "command": command,
                "time": time.time(),
                "exit_code": None,  # Unknown until PostToolUse
            })
            st["verifications"] = st["verifications"][-20:]
            state.save_state(state_file, st)

    # --- 1. Secret check (git add) ---
    if git_subcmd == "add":
        # Broad add check
        if git.is_broad_add(command):
            output.block(
                "BLOCKED: 'git add -A' / 'git add .' adds ALL files including secrets.\n\n"
                "Use explicit file listing instead: git add file1.py file2.py\n"
                "This prevents accidentally staging .env, *.key, *.pem, and other credential files.\n\n"
                "Known rationalization: 'I checked, there are no secrets' -- "
                "explicit listing is the policy regardless. .gitignore may have gaps."
            )
            return

        # Individual file check
        files = git.extract_file_paths(command)
        blocked = []
        for f in files:
            reason = is_secret_file(f)
            if reason:
                blocked.append((f, reason))

        if blocked:
            msg = "BLOCKED: git add targets secret/credential file(s).\n\n"
            for filepath, reason in blocked:
                msg += f"  - '{filepath}': {reason}\n"
            msg += (
                "\nGolden Principle #9: Ask Before High-Impact Changes.\n"
                "If this file is genuinely safe to commit:\n"
                "  1. Add it to .gitignore if it shouldn't be tracked\n"
                "  2. Or remove the secret content first\n\n"
                "Known rationalization: 'It's just a test file' -- "
                "test credentials are still credentials."
            )
            output.block(msg)
            return

    # --- 2. Branch check (commit/push/merge) ---
    if is_commit_push_or_merge(command) and not is_delete_only_push(command):
        target_root = resolve_commit_target_root(command)
        if git.is_protected_branch(cwd=target_root):
            output.block(
                "Create a feature branch first. Direct commits to "
                "main/master are not allowed. Run: git checkout -b <feature-name>"
            )
            return

    # --- 3. Verification checklist (commit/push) ---
    if is_commit_or_push(command) and not is_delete_only_push(command):
        # Evaluate the docs-only exemption against the repo the commit actually
        # targets (parsed from `cd <path> && git ...`), NOT the hook process cwd.
        target_root = resolve_commit_target_root(command)
        if not has_project_infrastructure(target_root):
            return  # docs-only repo, no verification needed
        if is_docs_only_commit(command, target_root) or is_pointer_only_commit(command, target_root):
            return  # docs- or pointer-only — nothing to test/lint

        state_file = state.get_state_file("claude-verification")
        st = state.load_state(state_file, {"verifications": [], "last_updated": time.time()})
        if state.is_stale(st):
            st = {"verifications": [], "last_updated": time.time()}

        # Recent verifications (within 30 minutes)
        recent = [v for v in st.get("verifications", [])
                  if time.time() - v["time"] < 1800]

        has_tests = any(
            re.search(r'test|jest|vitest|pytest|cargo\s+test|go\s+test|bash\s+-n', v["command"])
            for v in recent
        )
        has_lint = any(
            re.search(r'lint|eslint|tsc|mypy|ruff|clippy|bash\s+-n|shellcheck', v["command"])
            for v in recent
        )

        # Check that the most recent test and lint runs actually passed
        # Exit code 5 = pytest "no tests collected" — treat as passing
        failed_tests = [v for v in recent
                        if re.search(r'test|jest|vitest|pytest|cargo\s+test|go\s+test', v["command"])
                        and v.get("exit_code") is not None and v["exit_code"] not in (0, 5)]
        failed_lint = [v for v in recent
                       if re.search(r'lint|eslint|tsc|mypy|ruff|clippy|shellcheck', v["command"])
                       and v.get("exit_code") is not None and v["exit_code"] != 0]

        if failed_tests or failed_lint:
            msg = "PRE-COMPLETION CHECKLIST FAILED\n\n"
            msg += "Verification commands ran but FAILED:\n"
            if failed_tests:
                msg += f"  - Tests failed (exit code {failed_tests[-1]['exit_code']}): {failed_tests[-1]['command']}\n"
            if failed_lint:
                msg += f"  - Lint failed (exit code {failed_lint[-1]['exit_code']}): {failed_lint[-1]['command']}\n"
            msg += "\nFix the failures before committing. "
            msg += "Known rationalization: 'pre-existing failure, not my regression' — "
            msg += "a failing test is a failing test regardless of when it was introduced.\n"
            output.block(msg)
            return

        missing = []
        if not has_tests:
            missing.append("tests (npm test, pytest, cargo test, etc.)")
        if not has_lint:
            missing.append("linting/typecheck (npm run lint, tsc --noEmit, mypy, etc.)")

        if missing:
            msg = "PRE-COMPLETION CHECKLIST FAILED\n\n"
            msg += "You are about to commit/push but have NOT run:\n"
            for m in missing:
                msg += f"  - {m}\n"
            msg += "\nYou MUST run verification before committing. "
            msg += "Golden Principle #8: Verify Before Claiming Done.\n\n"
            msg += "Known rationalizations: 'I verified by reading the code' -- reading is not running. "
            msg += "'Changes are too small for tests' -- size does not exempt verification.\n\n"
            msg += "Run the missing checks first, then retry the commit.\n"
            msg += "If tests/linting don't apply to this repo, explain why to the user."
            output.block(msg)
            return

        # Commit message format check (only for git commit, not push)
        if re.search(r'\bgit\s+commit\b', command):
            # Skip if --amend or --no-edit (no new message expected)
            if re.search(r'--amend|--no-edit', command):
                return

            msg_text = extract_commit_message(command)
            if msg_text is None:
                prefixes_str = ", ".join(COMMIT_PREFIXES)
                output.block(
                    "COMMIT MESSAGE UNPARSEABLE\n\n"
                    "Could not extract commit message from command.\n"
                    f"Use: git commit -m \"{COMMIT_PREFIXES[0]} description\"\n"
                    f"Or: write message to a file, then git commit -F /path/to/msg.txt\n"
                    f"Allowed prefixes: {prefixes_str}\n\n"
                    "Known rationalization: 'The hook is parsing incorrectly' -- "
                    "fix the commit message format, not the command structure. "
                    "Working around a safety hook is a policy violation."
                )
                return

            has_prefix = any(msg_text.startswith(prefix) for prefix in COMMIT_PREFIXES)
            if not has_prefix:
                first_word = msg_text.split()[0] if msg_text.strip() else "(empty)"
                prefixes_str = ", ".join(COMMIT_PREFIXES)
                output.block(
                    "COMMIT MESSAGE FORMAT ERROR\n\n"
                    "Message must start with a conventional prefix.\n"
                    f"Allowed: {prefixes_str}\n"
                    f"Got: '{first_word}'\n\n"
                    'Example: git commit -m "feat: add user authentication"\n\n'
                    "Known rationalizations:\n"
                    "- 'It is just a WIP commit' -- WIP commits still need prefixes for git log readability.\n"
                    "- 'The hook is parsing incorrectly' -- fix the commit message, not the command format. "
                    "Circumventing a safety hook is a policy violation."
                )
                return


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        try:
            from _lib import output as _fallback_output
            _fallback_output.block(
                f"HOOK CRASH — git-safety-guard failed with: {exc}\n\n"
                f"Blocking to maintain safety. Report this error to the user.\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
        except Exception:
            import json
            print(json.dumps({
                "decision": "block",
                "reason": f"HOOK CRASH (fallback) — git-safety-guard: {exc}"
            }))
