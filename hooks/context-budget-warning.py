#!/usr/bin/env python3
"""Claude Code PostToolUse hook: warn when context budget is high.

Monitors context utilization percentage and injects warnings about
compaction and context management when thresholds are exceeded.

Thresholds (from Ch. 3 of The Harness Engineering Playbook):
- 70%: gentle reminder to be concise
- 85%: strong warning, suggest compaction
- 95%: critical, demand immediate compaction

Data sources checked (in priority order):
1. Event payload fields (e.g., context_window_usage, token_count) — from stdin JSON
2. Environment variables: CLAUDE_CONTEXT_PERCENT, CONTEXT_PERCENT, CLAUDE_CONTEXT_USAGE
3. Temp file: /tmp/claude-context-percent.txt (written by external tooling)
4. Tool call count heuristic — counts tool calls in metrics-logger JSONL for the
   current session and maps to an estimated context percentage.

KNOWN_LIMITATION:
    As of March 2026, Claude Code does not expose context window usage to hooks
    via the event payload, environment variables, or any documented mechanism.
    Sources 1-3 will return None in practice. Source 4 provides an imprecise but
    working heuristic based on tool call count, giving the hook a live signal
    even without official context exposure.
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Skip-interval: only re-parse JSONL every 10th tool call to avoid O(n^2)
_CACHE_RECOMPUTE_INTERVAL = 10


def _cache_path() -> Path | None:
    """Return session-specific cache file path, or None if no session."""
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        return None
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return Path(f"/tmp/claude-context-budget-cache-{session_hash}.json")


def _read_cache(cache_file: Path) -> dict | None:
    """Read cached estimate if it exists and is valid JSON."""
    try:
        with open(cache_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_file: Path, estimate: float, tool_count: int) -> None:
    """Write estimate to cache file."""
    try:
        with open(cache_file, "w") as f:
            json.dump({"estimate": estimate, "tool_count": tool_count, "ts": int(time.time())}, f)
    except OSError:
        pass  # cache write failure is non-fatal


def estimate_from_tool_count() -> float | None:
    """Estimate context usage from tool call count in current session.

    Uses a skip-interval cache: only re-parses the JSONL file every 10th
    tool call. Between parses, returns the cached estimate. This reduces
    the cost from O(n^2) over a session to O(n).

    Calibration assumptions (200K token window):
    - Average tool call consumes ~1000 tokens (input + output + reasoning)
    - 50 calls ~ 25% (50K tokens)
    - 100 calls ~ 50% (100K tokens)
    - 150 calls ~ 75% (150K tokens)
    - 200 calls ~ 95% (approaching limit)

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
            # Return cached value if fewer than 10 calls since last compute.
            # We don't know the exact current count yet, but we can use a
            # lightweight line count as a proxy to decide whether to recompute.
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

    # Linear mapping: 0 calls = 0%, 200 calls = 95%
    # Capped at 95% since we can't know the exact limit
    estimated = min(95.0, (count / 200.0) * 95.0)

    # Save to cache for skip-interval optimization
    if cache_file is not None:
        _write_cache(cache_file, estimated, count)

    return estimated


def get_context_percent(event: dict) -> float | None:
    """Try to read context utilization from available sources.

    Args:
        event: The PostToolUse event payload from stdin.

    Returns:
        Context usage as a float percentage (0-100), or None if unavailable.

    Sources checked (in order):
        1. Event payload — future-proofing for when Claude Code exposes context
           usage in hook events. Checks: context_window_usage, context_percent,
           token_usage.percent, session.context_percent.
        2. Environment variables — CLAUDE_CONTEXT_PERCENT, CONTEXT_PERCENT,
           CLAUDE_CONTEXT_USAGE. Not currently set by Claude Code.
        3. Temp file — /tmp/claude-context-percent.txt. Can be written by
           external monitoring (e.g., statusline scripts).
        4. Tool call count heuristic — counts tool calls from metrics-logger
           JSONL for the current session. Imprecise but provides a working
           signal when no other source is available.
    """
    # Source 1: Event payload fields (not currently populated by Claude Code)
    for field in ["context_window_usage", "context_percent", "context_usage"]:
        val = event.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue

    # Check nested structures that Claude Code might use in the future
    token_usage = event.get("token_usage", {})
    if isinstance(token_usage, dict):
        pct = token_usage.get("percent")
        if pct is not None:
            try:
                return float(pct)
            except (TypeError, ValueError):
                pass

    session = event.get("session", {})
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

    # Source 4: Heuristic from tool call count (via metrics-logger JSONL)
    # Imprecise but provides a working signal when no other source is available.
    # Calibration: based on typical 200K context window, ~1K tokens per tool call average.
    estimated = estimate_from_tool_count()
    if estimated is not None:
        return estimated

    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return  # malformed input, skip silently

    pct = get_context_percent(event)
    if pct is None:
        return  # can't determine context usage, skip silently

    if pct >= 95:
        print(json.dumps({
            "decision": "allow",
            "reason": (
                "You are a context-preservation agent. Context at {:.0f}% — output quality is actively degrading.\n\n"
                "Write a handoff file to /tmp/claude-handoff-{{session}}.md containing: current task, files modified, decisions made, what remains.\n\n"
                "Known rationalization: 'I'm almost done, one more edit' — this is the #1 cause of incoherent output. Stop and preserve state now."
            ).format(pct),
        }))
    elif pct >= 85:
        print(json.dumps({
            "decision": "allow",
            "reason": (
                "You are a context-preservation agent. Context at {:.0f}% — write critical state to /tmp/claude-handoff-{{session}}.md now: "
                "current task, files modified, decisions made, what remains. "
                "Delegate remaining exploratory work to subagents via the Agent tool to avoid filling this window."
            ).format(pct),
        }))
    elif pct >= 70:
        print(json.dumps({
            "decision": "allow",
            "reason": (
                "You are a concise communicator. Context at {:.0f}% — no recaps, no restating what the user said. "
                "Use codesight-mcp search_text instead of the Read tool for targeted lookups."
            ).format(pct),
        }))


if __name__ == "__main__":
    main()
