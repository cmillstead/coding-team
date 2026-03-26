#!/usr/bin/env python3
"""PostToolUse hook: enforce zero warnings from lint/typecheck commands."""
import json
import re
import sys


# Commands that this hook cares about
LINT_COMMAND_PATTERNS = [
    re.compile(p) for p in [
        r'\beslint\b', r'\btsc\b', r'\bmypy\b', r'\bruff\b',
        r'\bclippy\b', r'\bcargo\s+clippy\b', r'\bpylint\b', r'\bflake8\b',
        r'\bstylelint\b', r'\bng\s+build\b', r'\bng\s+serve\b',
        r'\bwebpack\b', r'\bvite\s+build\b',
        r'\bnpm\s+run\s+(lint|build)\b', r'\byarn\s+(lint|build)\b',
        r'\bpnpm\s+run\s+(lint|build)\b',
        r'\bcargo\s+(build|check)\b',
    ]
]

# Warning patterns in output
WARNING_PATTERNS = [
    re.compile(r'(?i)\bwarning:'),
    re.compile(r'⚠'),
    re.compile(r'\bWARN\b'),
    re.compile(r'\bW\d{4}\b'),  # pylint W0612 style
    re.compile(r'\d+\s+warnings?'),
]

# Lines matching these are false positives — ignore them
EXCLUSION_PATTERNS = [
    re.compile(r'\bnpm\s+warn\b'),
    re.compile(r'ExperimentalWarning'),
    re.compile(r'DeprecationWarning'),
    re.compile(r'--warn'),
    re.compile(r'warn\('),
]


def is_lint_command(command: str) -> bool:
    return any(p.search(command) for p in LINT_COMMAND_PATTERNS)


def is_excluded(line: str) -> bool:
    return any(p.search(line) for p in EXCLUSION_PATTERNS)


def has_warning(line: str) -> bool:
    return any(p.search(line) for p in WARNING_PATTERNS)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = data.get("tool_name", "")
    if tool_name != "Bash":
        return

    command = data.get("tool_input", {}).get("command", "")
    if not is_lint_command(command):
        return

    output = data.get("tool_output", "")
    if not output:
        return

    warning_lines = []
    for line in output.splitlines():
        if has_warning(line) and not is_excluded(line):
            warning_lines.append(line.strip())

    if warning_lines:
        sample = "\n".join(warning_lines[:5])
        extra = f"\n... and {len(warning_lines) - 5} more" if len(warning_lines) > 5 else ""
        print(json.dumps({
            "decision": "allow",
            "reason": (
                f"You are a zero-warning engineer. Fix all {len(warning_lines)} warnings before proceeding.\n\n"
                f"Sample warnings:\n{sample}{extra}\n\n"
                "The rationalization 'only warnings, no errors' is a compliance failure, "
                "not engineering judgment. Do not rationalize warnings as acceptable."
            ),
        }))
        return


if __name__ == "__main__":
    main()
