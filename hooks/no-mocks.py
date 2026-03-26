#!/usr/bin/env python3
"""Claude Code PostToolUse hook: reject test files that introduce mocking.

Fires after Edit/Write/Bash on test files. Scans the written content for mock
patterns. Edit/Write are blocked; Bash emits a warning only (shell commands
are too heuristic for reliable blocking).

Allowlist: add '# mock-ok: <reason>' on the same line or the line above
a mock import/usage to exempt it.
"""

import json
import re
import sys
from typing import Optional

# Patterns that indicate mocking (Python, TypeScript, Rust)
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

# File patterns that are test files
TEST_FILE_PATTERNS = [
    r'test[s]?[/_]',
    r'_test\.',
    r'\.test\.',
    r'\.spec\.',
    r'test_\w+\.',
]

ALLOWLIST_MARKER = 'mock-ok:'

# Regex patterns to extract target file paths from Bash write commands
BASH_WRITE_PATTERNS = [
    re.compile(r'(?:echo|printf)\s+.*\s*>>?\s*(\S+)'),
    re.compile(r'tee\s+(?:-a\s+)?(\S+)'),
    re.compile(r'sed\s+-i\s+.*\s+(\S+)'),
    re.compile(r'cat\s+.*>\s*(\S+)'),
]


def is_test_file(path: str) -> bool:
    return any(re.search(p, path) for p in TEST_FILE_PATTERNS)


def extract_bash_target(command: str) -> Optional[str]:
    """Extract the target file path from a Bash write command.

    Returns the path if the command is a recognizable write form,
    None for complex commands (pipelines, here-docs) or non-write commands.
    """
    for pattern in BASH_WRITE_PATTERNS:
        m = pattern.search(command)
        if m:
            return m.group(m.lastindex)
    return None


def check_command_for_mocks(command: str) -> list[str]:
    """Check a Bash command string for mock pattern names. Returns matched names."""
    matches = []
    for pattern, name in MOCK_PATTERNS:
        if re.search(pattern, command):
            matches.append(name)
    return matches


def check_content(content: str) -> list[dict]:
    """Return list of violations found in content."""
    violations = []
    lines = content.split('\n')

    for i, line in enumerate(lines):
        # Skip lines with allowlist marker
        if ALLOWLIST_MARKER in line:
            continue
        # Skip if previous line has allowlist marker
        if i > 0 and ALLOWLIST_MARKER in lines[i - 1]:
            continue

        for pattern, name in MOCK_PATTERNS:
            if re.search(pattern, line):
                violations.append({
                    'line': i + 1,
                    'pattern': name,
                    'text': line.strip()[:80],
                })
                break  # one violation per line is enough

    return violations


def handle_bash(tool_input: dict) -> None:
    """Handle Bash tool — warning only, never blocking."""
    command = tool_input.get('command', '')
    if not command:
        return

    target = extract_bash_target(command)
    if not target or not is_test_file(target):
        return

    matches = check_command_for_mocks(command)
    if not matches:
        return

    patterns_str = ', '.join(matches)
    print(json.dumps({
        "decision": "allow",
        "reason": (
            f"WARNING: Mock pattern detected in Bash command targeting test file "
            f"'{target}': {patterns_str}. "
            "Golden Principle #1: Real Over Mocks. "
            "Use real implementations instead of mocks."
        ),
    }))


def handle_edit_write(tool_name: str, tool_input: dict) -> None:
    """Handle Edit/Write tools — blocks on mock violations."""
    file_path = tool_input.get('file_path', '')
    if not file_path or not is_test_file(file_path):
        return

    # For Write, check the full content; for Edit, check new_string
    if tool_name == 'Write':
        content = tool_input.get('content', '')
    else:
        content = tool_input.get('new_string', '')

    if not content:
        return

    violations = check_content(content)
    if not violations:
        return

    # Block with remediation instructions (Golden Principle #1)
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

    # Output as blocking decision
    print(json.dumps({
        "decision": "block",
        "reason": msg,
    }))


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input, skip silently
    tool_name = event.get('tool_name', '')
    tool_input = event.get('tool_input', {})

    # Only check Edit, Write, and Bash tools
    if tool_name not in ('Edit', 'Write', 'Bash'):
        return

    if tool_name == 'Bash':
        handle_bash(tool_input)
    else:
        handle_edit_write(tool_name, tool_input)


if __name__ == '__main__':
    main()
