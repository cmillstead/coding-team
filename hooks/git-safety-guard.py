#!/usr/bin/env python3
"""Claude Code PreToolUse hook: consolidated git safety guard.

Combines secret-guard, branch-guard, and pre-completion-checklist into a single
hook with deterministic execution order:
  1. Secret check — block git add of secret files or broad adds
  2. Branch check — block commit/push/merge on main/master
  3. Verification checklist — require test+lint before commit/push

Also tracks verification commands (pytest, npm test, etc.) for checklist state.
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import glob
import re
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


def has_project_infrastructure() -> bool:
    """Check if the CWD has build/test infrastructure (not docs-only)."""
    cwd = os.getcwd()
    if any(os.path.exists(os.path.join(cwd, m)) for m in PROJECT_MARKERS):
        return True
    return any(glob.glob(os.path.join(cwd, g)) for g in GLOB_MARKERS)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ev = event.parse_event()
    if not ev:
        return

    tool_name = event.get_tool_name(ev)
    if tool_name != "Bash":
        return

    command = event.get_command(ev)
    if not command:
        return

    git_subcmd = git.extract_git_command(command)

    # --- Track verification commands (always, regardless of git command) ---
    if is_verification(command):
        state_file = state.get_state_file("claude-verification")
        st = state.load_state(state_file, {"verifications": [], "last_updated": time.time()})
        if state.is_stale(st):
            st = {"verifications": [], "last_updated": time.time()}
        st["verifications"].append({
            "command": command[:100],
            "time": time.time(),
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
    if git_subcmd in ("commit", "push", "merge"):
        if git.is_protected_branch():
            output.block(
                "Create a feature branch first. Direct commits to "
                "main/master are not allowed. Run: git checkout -b <feature-name>"
            )
            return

    # --- 3. Verification checklist (commit/push) ---
    if is_commit_or_push(command):
        if not has_project_infrastructure():
            return  # docs-only repo, no verification needed

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
