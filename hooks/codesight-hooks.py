#!/usr/bin/env python3
"""Codesight integration hooks: agent prompt injection + auto-reindex on file writes."""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import hashlib
import shutil
import subprocess
import time

from _lib.event import parse_event, get_tool_name, get_tool_input
from _lib.output import update_input

CODESIGHT_INSTRUCTION = (
    "\n\nMANDATORY SEARCH RULES: This repo is indexed in codesight-mcp. "
    "DO NOT use Grep, Bash grep, rg, or find to search code. "
    "Use mcp__codesight-mcp__search_text for text search and "
    "mcp__codesight-mcp__search_symbols for symbol search. "
    "Fetch these tools via ToolSearch first."
)

STYLE_INSTRUCTION = (
    "\n\nCODE STANDARDS: Before writing or reviewing code, read "
    "~/.claude/code-style.md for language-specific style rules. "
    "For design decisions and architectural trade-offs, read "
    "~/.claude/golden-principles.md. These files are authoritative — "
    "follow them over your trained defaults."
)

CODE_WORK_SIGNALS = [
    "implement", "write", "create", "fix", "refactor", "test",
    "build", "develop", "code", "function", "class", "module",
    "component", "endpoint", "api", "feature", "bug",
    "design", "architect", "plan",
]


def is_code_work(prompt: str) -> bool:
    """Check if the agent prompt involves code implementation or design."""
    prompt_lower = prompt.lower()
    return any(signal in prompt_lower for signal in CODE_WORK_SIGNALS)

SRC_PREFIX = os.path.expanduser("~/src/")
PROJECT_MARKERS = ("pyproject.toml", "package.json", "Cargo.toml", "go.mod")
DEBOUNCE_SECONDS = 30


def find_project_root(file_path: str) -> str | None:
    """Walk up from file_path to find the project root under ~/src/."""
    d = file_path
    while d != SRC_PREFIX.rstrip("/") and d != "/":
        d = os.path.dirname(d)
        for marker in PROJECT_MARKERS:
            if os.path.exists(os.path.join(d, marker)):
                return d
        if os.path.isdir(os.path.join(d, ".git")):
            return d
    return None


def should_debounce(project_root: str) -> bool:
    """Return True if reindex should be skipped (debounced)."""
    root_hash = hashlib.md5(project_root.encode()).hexdigest()
    debounce_file = f"/tmp/codesight-reindex-{root_hash}"
    now = int(time.time())
    try:
        with open(debounce_file) as f:
            last_run = int(f.read().strip())
        if now - last_run < DEBOUNCE_SECONDS:
            return True
    except (FileNotFoundError, ValueError):
        pass
    with open(debounce_file, "w") as f:
        f.write(str(now))
    return False


def find_codesight_binary() -> str | None:
    """Find the codesight-mcp binary on PATH, or None to gracefully degrade."""
    return shutil.which("codesight-mcp")


def handle_pre_agent(event: dict) -> None:
    """Inject codesight search instructions and code standards into Agent prompts."""
    tool_input = get_tool_input(event)
    prompt = tool_input.get("prompt", "")
    if not prompt:
        return

    injected = prompt + CODESIGHT_INSTRUCTION

    if is_code_work(prompt):
        injected += STYLE_INSTRUCTION

    update_input({"prompt": injected})


def handle_post_write(event: dict) -> None:
    """Auto-reindex codesight when source files under ~/src/ are written."""
    tool_input = get_tool_input(event)
    file_path = tool_input.get("file_path", "")
    if not file_path or not file_path.startswith(SRC_PREFIX):
        return

    project_root = find_project_root(file_path)
    if not project_root:
        return

    if should_debounce(project_root):
        return

    binary = find_codesight_binary()
    if not binary:
        return

    log_dir = "/private/tmp/claude"
    os.makedirs(log_dir, exist_ok=True)
    log_file = open(os.path.join(log_dir, "codesight-reindex.log"), "a")

    env = os.environ.copy()
    env["IRONMUNCH_ALLOWED_ROOTS"] = os.path.expanduser("~/src")

    subprocess.Popen(
        [binary, "index", project_root, "--no-ai"],
        stdout=log_file,
        stderr=log_file,
        env=env,
    )


def main() -> None:
    event = parse_event()
    if not event:
        return

    tool_name = get_tool_name(event)
    is_post = "tool_result" in event

    if not is_post and tool_name == "Agent":
        handle_pre_agent(event)
    elif is_post and tool_name in ("Write", "Edit"):
        handle_post_write(event)


if __name__ == "__main__":
    main()
