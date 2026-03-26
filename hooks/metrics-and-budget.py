#!/usr/bin/env python3
"""Claude Code PostToolUse hook: log tool usage metrics and warn on context budget.

Consolidates metrics-logger.py and context-budget-warning.py into a single hook.

Metrics logging runs first (always, never blocks, never fails).
Context budget check runs second and emits advisory warnings at thresholds.

Context budget thresholds:
- 50%: gentle reminder to be concise
- 70%: stronger conciseness reminder
- 85%: strong warning, suggest compaction
- 95%: critical, demand immediate compaction

Context data sources (in priority order):
1. Event payload fields (future-proofing)
2. Environment variables: CLAUDE_CONTEXT_PERCENT, CONTEXT_PERCENT, CLAUDE_CONTEXT_USAGE
3. Temp file: /tmp/claude-context-percent.txt
4. Tool call count heuristic from metrics JSONL
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from _lib import event as _event
from _lib import output as _output

# Skip-interval: only re-parse JSONL every 10th tool call to avoid O(n^2)
_CACHE_RECOMPUTE_INTERVAL = 10


# ---------------------------------------------------------------------------
# Metrics logging
# ---------------------------------------------------------------------------

def _extract_file(tool_input):
    """Extract file path from tool_input if available."""
    if not tool_input or not isinstance(tool_input, dict):
        return None
    # Direct file_path field (Read, Edit, Write)
    if "file_path" in tool_input:
        return tool_input["file_path"]
    # Command field — extract first path-like argument
    if "command" in tool_input:
        parts = tool_input["command"].split()
        for part in parts:
            if part.startswith("/"):
                return part
    # Pattern field (Glob)
    if "pattern" in tool_input and "path" in tool_input:
        return tool_input["path"]
    return None


def _log_metrics(event_data):
    """Write JSONL metric record. Wraps entire body in try/except — must never fail."""
    try:
        tool_name = event_data.get("tool_name", "unknown")
        tool_input = event_data.get("tool_input", {})

        metrics_dir = os.path.expanduser("~/.claude/metrics")
        os.makedirs(metrics_dir, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_path = os.path.join(metrics_dir, f"tool-usage-{today}.jsonl")

        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": tool_name,
            "file": _extract_file(tool_input),
            "session": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
        }

        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Context budget warning
# ---------------------------------------------------------------------------

def _cache_path():
    """Return session-specific cache file path, or None if no session."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        return None
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return Path(f"/tmp/claude-context-budget-cache-{session_hash}.json")


def _read_cache(cache_file):
    """Read cached estimate if it exists and is valid JSON."""
    try:
        with open(cache_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_file, estimate, tool_count):
    """Write estimate to cache file."""
    try:
        with open(cache_file, "w") as f:
            json.dump({"estimate": estimate, "tool_count": tool_count, "ts": int(time.time())}, f)
    except OSError:
        pass  # cache write failure is non-fatal


def _estimate_from_tool_count():
    """Estimate context usage from tool call count in current session.

    Uses a skip-interval cache: only re-parses the JSONL file every 10th
    tool call. Between parses, returns the cached estimate.

    Calibration assumptions (1M token window, Opus 4.6):
    - Average tool call consumes ~1000 tokens (input + output + reasoning)
    - 200 calls ~ 20%, 500 calls ~ 50%, 700 calls ~ 70%
    - 850 calls ~ 85%, 950 calls ~ 95%

    Returns None if metrics directory doesn't exist or no data for session.
    """
    metrics_dir = Path.home() / ".claude" / "metrics"
    if not metrics_dir.exists():
        return None

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        return None

    # Check cache before expensive JSONL parse
    cache_file = _cache_path()
    if cache_file is not None:
        cached = _read_cache(cache_file)
        if cached is not None:
            cached_count = cached.get("tool_count", 0)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_path = metrics_dir / f"tool-usage-{today}.jsonl"
            if log_path.exists():
                try:
                    with open(log_path) as f:
                        # Count lines cheaply (no JSON parsing)
                        line_count = sum(1 for _ in f)
                    if line_count - cached_count < _CACHE_RECOMPUTE_INTERVAL:
                        return cached.get("estimate")
                except OSError:
                    pass

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = metrics_dir / f"tool-usage-{today}.jsonl"

    if not log_path.exists():
        return None

    count = 0
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("session") == session_id:
                        count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None

    if count < 30:
        return None  # too few calls to estimate meaningfully

    # Linear mapping: 0 calls = 0%, 1000 calls = 95% (calibrated for 1M token window)
    estimated = min(95.0, (count / 1000.0) * 95.0)

    # Save to cache for skip-interval optimization
    if cache_file is not None:
        _write_cache(cache_file, estimated, count)

    return estimated


def _get_context_percent(event_data):
    """Try to read context utilization from available sources.

    Sources checked (in order):
        1. Event payload fields
        2. Environment variables
        3. Temp file /tmp/claude-context-percent.txt
        4. Tool call count heuristic
    """
    # Source 1: Event payload fields (not currently populated by Claude Code)
    for field in ["context_window_usage", "context_percent", "context_usage"]:
        val = event_data.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue

    # Check nested structures that Claude Code might use in the future
    token_usage = event_data.get("token_usage", {})
    if isinstance(token_usage, dict):
        pct = token_usage.get("percent")
        if pct is not None:
            try:
                return float(pct)
            except (TypeError, ValueError):
                pass

    session = event_data.get("session", {})
    if isinstance(session, dict):
        pct = session.get("context_percent")
        if pct is not None:
            try:
                return float(pct)
            except (TypeError, ValueError):
                pass

    # Source 2: Environment variables (not currently set by Claude Code)
    for var in ["CLAUDE_CONTEXT_PERCENT", "CONTEXT_PERCENT", "CLAUDE_CONTEXT_USAGE"]:
        val = os.environ.get(var)
        if val:
            try:
                return float(val.strip().rstrip("%"))
            except ValueError:
                continue

    # Source 3: Temp file (written by external tooling, e.g., statusline)
    try:
        with open("/tmp/claude-context-percent.txt") as f:
            return float(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass

    # Source 4: Heuristic from tool call count (via metrics JSONL)
    estimated = _estimate_from_tool_count()
    if estimated is not None:
        return estimated

    return None


def _check_context_budget(event_data):
    """Check context budget and emit advisory warning if threshold exceeded."""
    pct = _get_context_percent(event_data)
    if pct is None:
        return  # can't determine context usage, skip silently

    if pct >= 95:
        _output.advisory(
            "You are a context-preservation agent. Context at {:.0f}% — output quality is actively degrading.\n\n"
            "Write a handoff file to /tmp/claude-handoff-{{session}}.md containing: current task, files modified, decisions made, what remains.\n\n"
            "Known rationalization: 'I'm almost done, one more edit' — this is the #1 cause of incoherent output. Stop and preserve state now.".format(pct)
        )
    elif pct >= 85:
        _output.advisory(
            "You are a context-preservation agent. Context at {:.0f}% — write critical state to /tmp/claude-handoff-{{session}}.md now: "
            "current task, files modified, decisions made, what remains. "
            "Delegate remaining exploratory work to subagents via the Agent tool to avoid filling this window.".format(pct)
        )
    elif pct >= 70:
        _output.advisory(
            "You are a concise communicator. Context at {:.0f}% — no recaps, no restating what the user said. "
            "Use codesight-mcp search_text instead of the Read tool for targeted lookups.".format(pct)
        )
    elif pct >= 50:
        _output.advisory(
            "You are a concise communicator. Context at {:.0f}% — start being concise. "
            "Shorter explanations, less recapping, no restating what the user said.".format(pct)
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    event_data = _event.parse_event()

    # Metrics logging runs first — always, never blocks, never fails
    _log_metrics(event_data)

    # Context budget check — emits advisory warnings at thresholds
    _check_context_budget(event_data)


if __name__ == "__main__":
    main()
