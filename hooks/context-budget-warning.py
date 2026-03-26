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

KNOWN_LIMITATION:
    As of March 2026, Claude Code does not expose context window usage to hooks
    via the event payload, environment variables, or any documented mechanism.
    All three data sources above will return None in practice, causing this hook
    to silently no-op. This is by design — the hook is deployed as ready
    infrastructure so that when Claude Code adds context exposure (via event
    fields or env vars), this hook activates automatically without redeployment.
"""

import json
import os
import sys


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
