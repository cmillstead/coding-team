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

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def estimate_from_tool_count() -> float | None:
    """Estimate context usage from tool call count in current session.

    Reads metrics-logger JSONL for today, counts tool calls matching
    the current session ID. Maps count to estimated percentage using
    a conservative linear model.

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
                "CRITICAL: Context window is at {:.0f}%. You are about to lose coherence.\n\n"
                "IMMEDIATELY:\n"
                "1. Write key decisions and current state to a NOTES.md or PLANS.md file\n"
                "2. Request /compact or manual compaction\n"
                "3. After compaction, re-read NOTES.md to restore context\n\n"
                "Do NOT continue working without compaction — context rot is degrading your output quality."
            ).format(pct),
        }))
    elif pct >= 85:
        print(json.dumps({
            "decision": "allow",
            "reason": (
                "WARNING: Context window at {:.0f}%. Quality may degrade.\n"
                "Consider: save important state to a file, then compact. "
                "Use sub-agents for remaining exploratory work to avoid filling this window further."
            ).format(pct),
        }))
    elif pct >= 70:
        print(json.dumps({
            "decision": "allow",
            "reason": (
                "Context at {:.0f}%. Be concise — avoid loading unnecessary files. "
                "Use codesight-mcp tools instead of reading full files when possible."
            ).format(pct),
        }))


if __name__ == "__main__":
    main()
