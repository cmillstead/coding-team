#!/usr/bin/env python3
"""Claude Code PreToolUse hook: consolidated write guard.

You are a file-write integrity guardian. Consolidates 4 guards into one:
1. Phase 5 edit guard — blocks orchestrator edits to non-allowlisted files during execution
2. Migration guard — blocks edits to deployed migration files
3. No-mocks guard — blocks mock usage in test files
4. Identity framing check — advisory when agent/skill files lack identity framing

Execution order: first block wins, but advisory checks always run.
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import json
import re
import time
from pathlib import Path

from _lib import event as _event
from _lib import output as _output

# ---------------------------------------------------------------------------
# Phase 5 edit guard constants
# ---------------------------------------------------------------------------
SESSION_FILE = Path("/tmp/coding-team-session.json")
MAX_AGE_SECONDS = 2 * 60 * 60  # 2 hours
ACTIVE_MARKER = Path("/tmp/coding-team-active")


def is_orchestrator_file(file_path: str) -> bool:
    """Return True only for files the orchestrator may always edit during Phase 5."""
    path_str = str(file_path)
    if path_str.startswith("/tmp"):
        return True
    if "/Documents/obsidian-vault/" in path_str:
        return True
    if "/memory/" in path_str or path_str.endswith("/memory"):
        return True
    return False


# Instruction files: high impact surface — always delegate regardless of edit size.
# A 1-line change to an agent prompt can cascade through the entire pipeline.
INSTRUCTION_PATTERNS = [
    "/agents/",
    "/phases/",
    "/prompts/",
    "/skills/",
    "/hooks/",
    "CLAUDE.md",
    "SKILL.md",
]


def is_instruction_file(file_path: str) -> bool:
    """Return True for files that MUST be delegated — high impact surface."""
    path_str = str(file_path)
    return any(pattern in path_str for pattern in INSTRUCTION_PATTERNS)


def read_session() -> tuple[dict | None, bool]:
    """Read and validate the session file.

    Returns (session_dict, had_error).
    """
    if not SESSION_FILE.exists():
        return None, False
    try:
        data = json.loads(SESSION_FILE.read_text())
    except json.JSONDecodeError:
        return None, True
    except OSError:
        return None, False
    try:
        phase = data["phase"]
        ts = data["ts"]
    except KeyError:
        return None, True
    if time.time() - ts > MAX_AGE_SECONDS:
        return None, False
    return {"phase": phase, "ts": ts}, False


def check_phase5(file_path: str) -> str | None:
    """Check coding-team session edit guard. Returns block reason or None.

    Blocks orchestrator edits to non-allowlisted files during ANY active
    coding-team session (phase 'execution' or 'active').

    Tamper detection: if the active marker exists but the session JSON is
    missing, the session file was deleted mid-session — block to maintain safety.
    """
    session, had_error = read_session()
    if had_error:
        return (
            "BLOCKED: coding-team session file is corrupt or unreadable. "
            "Cannot determine session state — blocking to maintain safety. "
            "Delete /tmp/coding-team-session.json if no coding-team session is active."
        )
    if session is None:
        # Session file missing — check if a session SHOULD be active
        if ACTIVE_MARKER.exists():
            # Check marker age — stale markers from crashed/compacted sessions
            # should be cleaned up, not block indefinitely
            try:
                marker_content = ACTIVE_MARKER.read_text().strip()
                marker_ts = float(marker_content) if marker_content else 0
            except (ValueError, OSError):
                marker_ts = 0
            marker_age = time.time() - marker_ts if marker_ts > 0 else float("inf")
            if marker_age > MAX_AGE_SECONDS:
                # Stale marker — clean up silently and allow
                try:
                    ACTIVE_MARKER.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
            return (
                "BLOCKED: coding-team session file is missing but the session marker "
                "(/tmp/coding-team-active) still exists. This suggests the session file "
                "was deleted mid-session — blocking to maintain safety.\n\n"
                "If the session is genuinely over, complete it through Phase 6 "
                "(which cleans up both files via the lifecycle hook).\n\n"
                "Known rationalization: 'The session file is blocking my edits' — "
                "that IS the correct behavior. Delegate edits through the Agent tool."
            )
        return None
    if session["phase"] not in ("execution", "active"):
        return None
    if is_orchestrator_file(file_path):
        return None

    # Instruction files: ALWAYS delegate — high impact surface regardless of edit size.
    # Source code: allowed for small edits (orchestrator uses ≤20 line threshold).
    if is_instruction_file(file_path):
        return (
            f"BLOCKED: Instruction file edit during active coding-team session. "
            f"Instruction files (agents, phases, prompts, skills, hooks, CLAUDE.md) "
            f"ALWAYS go through the Agent tool — a 1-line change can cascade.\n\n"
            f"File: {file_path}\n"
            f"Use the Agent tool to dispatch this edit with PROMPT_CRAFT_ADVISORY.\n\n"
            f"Known rationalization: 'This instruction file change is trivial' — "
            f"impact surface determines routing, not perceived complexity."
        )

    # Non-instruction source code: allow (orchestrator judges ≤20 line threshold)
    return None


# ---------------------------------------------------------------------------
# Migration guard constants
# ---------------------------------------------------------------------------
MIGRATION_DIR_NAMES = {"migrations", "versions", "migrate"}

MIGRATION_PATH_PATTERNS = [
    ("migrations",),
    ("alembic", "versions"),
    ("db", "migrate"),
    ("prisma", "migrations"),
]

MIGRATION_FILE_PATTERN = re.compile(r'^\d+[_\-]')


def is_migration_file(filepath: str) -> bool:
    """Check if a file path points to a migration file using structural path matching."""
    path = Path(filepath)
    parts = path.parts
    for pattern in MIGRATION_PATH_PATTERNS:
        pattern_len = len(pattern)
        for i in range(len(parts) - pattern_len):
            if parts[i:i + pattern_len] == pattern:
                return True
    if MIGRATION_FILE_PATTERN.match(path.name):
        for part in parts[:-1]:
            if part.lower() in MIGRATION_DIR_NAMES:
                return True
    return False


def check_migration(tool_name: str, file_path: str) -> str | None:
    """Check migration guard. Returns block reason or None."""
    if tool_name == "Write" and not Path(file_path).exists():
        return None  # New file creation is allowed

    if not is_migration_file(file_path):
        return None

    path = Path(file_path)
    return (
        f"BLOCKED: editing deployed migration file '{path.name}'.\n\n"
        f"Deployed migrations are immutable. Create a new migration instead.\n"
        f"See rules/migration-files.md for migration file rules.\n\n"
        f"Golden Principle #9: Ask Before High-Impact Changes.\n"
        f"Modifying a deployed migration can cause:\n"
        f"  - Schema drift between environments\n"
        f"  - Failed rollbacks\n"
        f"  - Data loss\n\n"
        f"Known rationalization: 'It's just a comment/docstring change' — "
        f"any edit to deployed migrations risks inconsistency."
    )


# ---------------------------------------------------------------------------
# No-mocks guard constants
# ---------------------------------------------------------------------------
MOCK_PATTERNS = [
    # Python
    (r'\bfrom\s+unittest\.mock\s+import\b', 'unittest.mock import'),
    (r'\bfrom\s+unittest\s+import\s+mock\b', 'unittest mock import'),
    (r'\bimport\s+unittest\.mock\b', 'unittest.mock import'),
    (r'\bmock\.patch\b', 'mock.patch'),
    (r'\b@patch\b', '@patch decorator'),
    (r'\bMagicMock\b', 'MagicMock'),
    (r'\bAsyncMock\b', 'AsyncMock'),
    (r'\bPropertyMock\b', 'PropertyMock'),
    (r'\bmonkeypatch\b', 'monkeypatch'),
    (r'\bcreate_autospec\b', 'create_autospec'),
    # TypeScript/JavaScript
    (r'\bjest\.mock\b', 'jest.mock'),
    (r'\bjest\.spyOn\b', 'jest.spyOn'),
    (r'\bvi\.mock\b', 'vi.mock (vitest)'),
    (r'\bvi\.spyOn\b', 'vi.spyOn (vitest)'),
    (r'\bsinon\.\w+\b', 'sinon'),
    # Rust
    (r'\b#\[mockall::automock\]', 'mockall automock'),
    (r'\bmock!\s*\{', 'mock! macro'),
]

TEST_FILE_PATTERNS = [
    r'test[s]?[/_]',
    r'_test\.',
    r'\.test\.',
    r'\.spec\.',
    r'test_\w+\.',
]

ALLOWLIST_MARKER = 'mock-ok:'


def is_test_file(path: str) -> bool:
    """Check if a file path is a test file."""
    return any(re.search(p, path) for p in TEST_FILE_PATTERNS)


def check_content_for_mocks(content: str) -> list[dict]:
    """Return list of mock violations found in content."""
    violations = []
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if ALLOWLIST_MARKER in line:
            continue
        if i > 0 and ALLOWLIST_MARKER in lines[i - 1]:
            continue
        for pattern, name in MOCK_PATTERNS:
            if re.search(pattern, line):
                violations.append({
                    'line': i + 1,
                    'pattern': name,
                    'text': line.strip()[:80],
                })
                break
    return violations


def check_no_mocks(tool_name: str, tool_input: dict) -> str | None:
    """Check no-mocks guard. Returns block reason or None."""
    file_path = tool_input.get('file_path', '')
    if not file_path or not is_test_file(file_path):
        return None

    if tool_name == 'Write':
        content = tool_input.get('content', '')
    else:
        content = tool_input.get('new_string', '')

    if not content:
        return None

    violations = check_content_for_mocks(content)
    if not violations:
        return None

    msg = "BLOCKED: Mock usage detected in test file.\n\n"
    msg += "Golden Principle #1: Real Over Mocks.\n"
    msg += "This codebase requires REAL implementations, not mocks.\n\n"
    msg += "Violations found:\n"
    for v in violations:
        msg += f"  Line {v['line']}: {v['pattern']} → {v['text']}\n"
    msg += "\n"
    msg += "REMEDIATION — replace mocks with real implementations:\n"
    msg += "  - Database:     Use SQLite temp DB or Docker test container\n"
    msg += "  - HTTP client:  Use httpx.AsyncClient(app=app) or real test server\n"
    msg += "  - File system:  Use tempfile.mkdtemp() or tmp_path fixture\n"
    msg += "  - Redis:        Use Docker test container or fakeredis\n"
    msg += "  - External API: ONLY mock if no sandbox/test mode exists\n"
    msg += "                  In that case, add '# mock-ok: <reason>' on the line\n"
    msg += "\n"
    msg += "If mocking is truly unavoidable (paid API, no sandbox), add:\n"
    msg += "  # mock-ok: <specific reason why real impl is impossible>\n"
    return msg


# ---------------------------------------------------------------------------
# Identity framing check constants
# ---------------------------------------------------------------------------
IDENTITY_FILE_PATTERNS = [
    r"\.claude/agents/.*\.md$",
    r"\.claude/skills/.*/SKILL\.md$",
    r"agents/.*\.md$",
    r"skills/.*/SKILL\.md$",
]

IDENTITY_MARKERS = [
    r"^you are ",
    r"^your role",
    r"^as the ",
    r"^you serve as",
]


def is_instruction_file(file_path: str) -> bool:
    """Check if the file path matches known instruction file patterns."""
    for pattern in IDENTITY_FILE_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def has_identity_framing(content: str) -> bool:
    """Check if content starts with identity framing (after frontmatter/headers)."""
    if not content:
        return False

    lines = content.split("\n")
    in_frontmatter = False
    content_started = False

    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            content_started = True
            continue
        if content_started or not stripped.startswith("#"):
            for marker in IDENTITY_MARKERS:
                if re.match(marker, stripped, re.IGNORECASE):
                    return True
            return False

    return False


def check_identity_framing(tool_name: str, tool_input: dict) -> str | None:
    """Check identity framing. Returns advisory reason or None."""
    file_path = tool_input.get("file_path", "")

    if not file_path or not is_instruction_file(file_path):
        return None

    # For Write, check full content; for Edit, check new_string
    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    if not has_identity_framing(content):
        return (
            f"Identity framing missing in {file_path}.\n"
            f"Agent/skill instruction files should start with identity framing: "
            f"'You are the [role]' — this sets behavioral defaults stronger than prohibitions.\n"
            f"See skill-files.md rule for guidance."
        )
    return None


# ---------------------------------------------------------------------------
# Path safety check constants (Case study #35)
# ---------------------------------------------------------------------------
PATH_SAFETY_PATTERNS = [
    (re.compile(r'(?:str\(|f["\'])\s*\w*path\w*.*\bin\b', re.I), 'string "in" check on path variable'),
    (re.compile(r'\w*path\w*\.startswith\s*\(', re.I), '.startswith() on path string'),
    (re.compile(r'["\'][^"\']*[/\\][^"\']*["\']\s+in\s+\w*path', re.I), 'string literal path in check'),
]

PATH_SAFE_PATTERNS = [
    re.compile(r'\.is_relative_to\('),
    re.compile(r'\.parts\b'),
    re.compile(r'Path\('),
]


def check_path_safety(tool_name: str, tool_input: dict) -> str | None:
    """Advisory: warn when Python code uses string operations on paths instead of Path API.

    Case study #35: string operations on paths are bypassable via substring collisions.
    """
    file_path = tool_input.get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        return None

    if tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        content = tool_input.get("new_string", "")

    if not content:
        return None

    violations = []
    for pattern, name in PATH_SAFETY_PATTERNS:
        if pattern.search(content):
            # Check if the same content also uses safe Path APIs (allow if so)
            if any(safe.search(content) for safe in PATH_SAFE_PATTERNS):
                continue
            violations.append(name)

    if not violations:
        return None

    return (
        f"Path safety advisory: {', '.join(violations)}.\n"
        f"Case study #35: string operations on paths are bypassable via substring collisions.\n"
        f"Use Path.is_relative_to(), Path.parts, or Path() for structural path matching.\n"
        f"Known rationalization: 'startswith is good enough' — it isn't when paths contain '../' or overlapping prefixes."
    )


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
def main():
    event = _event.parse_event()
    if not event:
        return

    tool_name = _event.get_tool_name(event)
    if tool_name not in ("Edit", "Write"):
        return  # Silent return for non-Edit/Write tools

    tool_input = _event.get_tool_input(event)
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    # 1. Phase 5 edit guard (blocking)
    reason = check_phase5(file_path)
    if reason:
        _output.block(reason)
        return

    # 2. Migration guard (blocking)
    reason = check_migration(tool_name, file_path)
    if reason:
        _output.block(reason)
        return

    # 3. No-mocks guard (blocking)
    reason = check_no_mocks(tool_name, tool_input)
    if reason:
        _output.block(reason)
        return

    # 4. Identity framing check (advisory — runs even if no block occurred)
    reason = check_identity_framing(tool_name, tool_input)
    if reason:
        _output.advisory(reason)

    # 5. Path safety check (advisory)
    reason = check_path_safety(tool_name, tool_input)
    if reason:
        _output.advisory(reason)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        try:
            from _lib import output as _fallback_output
            _fallback_output.block(
                f"HOOK CRASH — write-guard failed with: {exc}\n\n"
                f"Blocking to maintain safety. Report this error to the user.\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
        except Exception:
            # Last resort: raw JSON to stdout if even _lib is broken
            import json
            print(json.dumps({
                "decision": "block",
                "reason": f"HOOK CRASH (fallback) — write-guard: {exc}"
            }))
