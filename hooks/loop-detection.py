#!/usr/bin/env python3
"""Claude Code PostToolUse hook: detect doom loops and inject recovery strategies.

Monitors repeated Bash failures for the same command pattern. After MAX_RETRIES
failures of the same pattern within 5 minutes, injects structured recovery
prompts with alternative strategies based on the failure type.

Failure categories: build, test, permission, network, unknown.
"""
import hashlib
import json
import os
import sys
import time

MAX_RETRIES = 3
STATE_DIR = "/tmp"
STALE_SECONDS = 3600

FAILURE_PATTERNS = {
    "build": {
        "markers": ["cannot find module", "module not found", "no such file or directory",
                     "compilation failed", "build failed", "syntax error", "import error",
                     "modulenotfounderror", "npm err", "cargo error", "tsc error"],
        "strategies": [
            "1. Read the FULL error output — do not skim",
            "2. Check if dependencies are installed: review package.json/pyproject.toml/Cargo.toml",
            "3. Verify import paths are correct relative to the project root",
            "4. Try a minimal reproduction: isolate the failing module",
            "5. Check if the file you're importing actually exists at the expected path",
        ],
    },
    "test": {
        "markers": ["assert", "expected", "actual", "test failed", "pytest", "jest",
                     "mocha", "unittest", "failures=", "errors=", "fail"],
        "strategies": [
            "1. Run the SINGLE failing test in isolation, not the full suite",
            "2. Read the assertion diff carefully — what was expected vs actual?",
            "3. Check test fixtures and setup — is the test environment correct?",
            "4. Add debug logging BEFORE the assertion to inspect intermediate state",
            "5. If the test tests YOUR change, verify the change logic, not the test",
        ],
    },
    "permission": {
        "markers": ["permission denied", "eacces", "operation not permitted",
                     "read-only file system", "not writable"],
        "strategies": [
            "1. Verify the target path exists: use ls -la on the parent directory",
            "2. Use absolute paths — relative paths may resolve unexpectedly",
            "3. Check if you're writing to a read-only location (/usr, /System, etc.)",
            "4. Try a different output location (e.g., /tmp/ for temporary files)",
            "5. Ask the user if elevated permissions are needed",
        ],
    },
    "network": {
        "markers": ["connection refused", "timeout", "econnrefused", "enotfound",
                     "network unreachable", "could not resolve", "ssl", "certificate"],
        "strategies": [
            "1. Verify the URL/endpoint is correct — typos are common",
            "2. Check if the service is running (for local services)",
            "3. Try an offline alternative if available",
            "4. If SSL error, check certificate validity",
            "5. Ask the user about network/proxy configuration",
        ],
    },
}


def get_state_file():
    session_id = os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "default"))
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return os.path.join(STATE_DIR, f"claude-loop-detection-{h}.json")


def load_state(path):
    try:
        with open(path) as f:
            state = json.load(f)
        if time.time() - state.get("last_updated", 0) > STALE_SECONDS:
            return {"failures": [], "last_updated": time.time()}
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return {"failures": [], "last_updated": time.time()}


def save_state(path, state):
    state["last_updated"] = time.time()
    with open(path, "w") as f:
        json.dump(state, f)


def normalize_command(cmd):
    parts = cmd.strip().split()
    if not parts:
        return cmd
    normalized = []
    for part in parts[:5]:
        if "/" in part and not part.startswith("-"):
            normalized.append(os.path.basename(part))
        else:
            normalized.append(part)
    return " ".join(normalized)


def classify_failure(stdout, stderr):
    combined = (stdout + " " + stderr).lower()
    for category, info in FAILURE_PATTERNS.items():
        for marker in info["markers"]:
            if marker in combined:
                return category
    return "unknown"


def build_recovery_message(pattern, count, category):
    header = (
        f"You are a recovery strategist. '{pattern}' has failed {count} times in 5 minutes "
        f"— retrying the same approach will fail again.\n\n"
        f"Known rationalization: 'This attempt is slightly different' — it is not. "
        f"The failure pattern is identical."
    )
    if category != "unknown" and category in FAILURE_PATTERNS:
        strategies = "\n".join(FAILURE_PATTERNS[category]["strategies"])
        return (
            f"{header}\n\nFailure type: {category.upper()}\n\n"
            f"Your next action MUST be one of these alternatives:\n{strategies}\n\n"
            f"If none work after 1 attempt each, ask the user."
        )
    return (
        f"{header}\n\nFailure type: UNKNOWN\n\n"
        f"Your next action MUST be one of:\n"
        f"1. Describe what you were trying to achieve (the GOAL, not the command)\n"
        f"2. List the {count} approaches you already tried\n"
        f"3. Identify what changed between working and broken state\n"
        f"4. Try ONE different approach (different tool, different path, different method)\n"
        f"5. If that fails too, ask the user — do not guess further"
    )


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    tool_name = event.get("tool_name", "")
    if tool_name != "Bash":
        return

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})
    command = tool_input.get("command", "")
    if not command:
        return

    stdout = tool_result.get("stdout", "") if isinstance(tool_result, dict) else str(tool_result)
    stderr = tool_result.get("stderr", "") if isinstance(tool_result, dict) else ""
    exit_code = tool_result.get("exit_code", 0) if isinstance(tool_result, dict) else None

    is_failure = False
    if exit_code is not None and exit_code != 0:
        is_failure = True
    elif any(marker in stdout.lower() for marker in ["error", "failed", "failure", "exception", "traceback"]):
        is_failure = True
    elif any(marker in stderr.lower() for marker in ["error", "failed", "failure"]):
        is_failure = True

    state_file = get_state_file()
    state = load_state(state_file)

    if is_failure:
        pattern = normalize_command(command)
        category = classify_failure(stdout, stderr)
        state["failures"].append({"pattern": pattern, "command": command[:200], "category": category, "time": time.time()})
        state["failures"] = state["failures"][-20:]
        save_state(state_file, state)

        recent = [f for f in state["failures"] if f["pattern"] == pattern and time.time() - f["time"] < 300]
        if len(recent) >= MAX_RETRIES:
            categories = [f.get("category", "unknown") for f in recent]
            dominant = max(set(categories), key=categories.count)
            msg = build_recovery_message(pattern, len(recent), dominant)
            print(json.dumps({"decision": "allow", "reason": msg}))
            return
    else:
        pattern = normalize_command(command)
        state["failures"] = [f for f in state["failures"] if f["pattern"] != pattern]
        save_state(state_file, state)


if __name__ == "__main__":
    main()
