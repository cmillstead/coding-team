#!/usr/bin/env python3
"""Claude Code SessionStart hook: analyze metrics for anomalies.

Reads JSONL files from ~/.claude/metrics/ (written by metrics-logger.py),
computes aggregate statistics for recent sessions, and surfaces anomalies:
- High Edit:Read ratio (>3:1) suggests stale context
- Excessive Bash calls (>30) suggests retry loops
- Long sessions (200+ tool calls) need compaction
- Low search usage — many edits with no Grep/Glob
"""
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.output import advisory

METRICS_DIR = Path.home() / ".claude" / "metrics"
QUALITY_TRACKER_PATH = Path.home() / ".claude" / "agent-quality-tracker.jsonl"
MAX_FILES_TO_CHECK = 3


def load_recent_metrics():
    if not METRICS_DIR.exists():
        return []
    files = sorted(METRICS_DIR.glob("tool-usage-*.jsonl"), reverse=True)
    records = []
    for f in files[:MAX_FILES_TO_CHECK]:
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            continue
    return records


def analyze_session(records, session_id):
    session_records = [r for r in records if r.get("session") == session_id]
    if len(session_records) < 10:
        return []
    anomalies = []
    tool_counts = Counter(r.get("tool", "unknown") for r in session_records)

    edits = tool_counts.get("Edit", 0)
    reads = tool_counts.get("Read", 0)
    if edits > 6 and reads > 0 and edits / reads > 3:
        anomalies.append(
            f"High Edit:Read ratio ({edits}:{reads} = {edits/reads:.1f}:1)"
            " — re-read files before editing to avoid stale overwrites"
        )
    elif edits > 3 and reads == 0:
        anomalies.append(f"{edits} Edit calls with 0 Read calls — always read before editing")

    bash_count = tool_counts.get("Bash", 0)
    if bash_count > 30:
        anomalies.append(f"{bash_count} Bash calls in session — likely retry loop. Use alternative approaches instead of re-running the same command.")

    total = len(session_records)
    if total > 200:
        anomalies.append(
            f"{total} tool calls in session"
            " — compaction needed to avoid context degradation"
        )

    searches = tool_counts.get("Grep", 0) + tool_counts.get("Glob", 0)
    if edits > 10 and searches == 0:
        anomalies.append(
            f"{edits} edits with no search calls"
            " — use Grep tool and Glob tool to verify changes across codebase"
        )

    # High agent dispatch ratio
    agent_calls = tool_counts.get("Agent", 0)
    if total > 0 and agent_calls / total > 0.4:
        pct = agent_calls / total * 100
        anomalies.append(
            f"High agent dispatch ratio ({agent_calls}/{total} = {pct:.0f}%)"
            " — consider consolidating worker prompts"
        )

    return anomalies


def summarize_sessions(sessions, current_session, max_sessions=3):
    """Compute per-session cost summary: total calls, top tools, agent count, skills."""
    summaries = []
    for sid, records in sessions.items():
        if sid == current_session:
            continue
        total = len(records)
        if total == 0:
            continue
        tool_counts = Counter(r.get("tool", "unknown") for r in records)
        top5 = tool_counts.most_common(5)
        top5_str = ", ".join(f"{tool}:{count}" for tool, count in top5)

        parts = [f"{sid}: {total} calls ({top5_str})"]

        # Collect invoked skills from Skill tool calls
        skills = set()
        for r in records:
            if r.get("tool") == "Skill":
                skill_name = r.get("skill")
                if skill_name:
                    skills.add(skill_name)
        if skills:
            parts.append(f"skills: {', '.join(sorted(skills))}")

        summaries.append("- " + ", ".join(parts))
        if len(summaries) >= max_sessions:
            break
    return summaries


def aggregate_by_branch(records):
    """Group sessions by git branch and compute aggregate stats.

    Returns a dict mapping branch name to:
      - total_calls: int
      - session_count: int
      - top_tools: list of (tool, count) tuples (top 5)
      - sessions: list of session IDs
    Only branches with 2+ sessions are included.
    """
    branch_sessions = {}
    for r in records:
        branch = r.get("branch")
        if not branch:
            continue
        sid = r.get("session", "unknown")
        if branch not in branch_sessions:
            branch_sessions[branch] = {}
        if sid not in branch_sessions[branch]:
            branch_sessions[branch][sid] = []
        branch_sessions[branch][sid].append(r)

    result = {}
    for branch, sessions in branch_sessions.items():
        if len(sessions) < 2:
            continue
        all_records = []
        for sid_records in sessions.values():
            all_records.extend(sid_records)
        tool_counts = Counter(r.get("tool", "unknown") for r in all_records)
        result[branch] = {
            "total_calls": len(all_records),
            "session_count": len(sessions),
            "top_tools": tool_counts.most_common(5),
            "sessions": sorted(sessions.keys()),
        }
    return result


def format_branch_summary(branch_data):
    """Format branch aggregation data into a human-readable string.

    Args:
        branch_data: dict from aggregate_by_branch()

    Returns:
        Formatted string, or empty string if no data.
    """
    if not branch_data:
        return ""
    lines = []
    for branch, info in sorted(branch_data.items()):
        top_str = ", ".join(f"{t}:{c}" for t, c in info["top_tools"])
        lines.append(
            f"- {branch}: {info['total_calls']} calls across "
            f"{info['session_count']} sessions ({top_str})"
        )
    return "Branch cost summary:\n" + "\n".join(lines)


def get_pr_throughput():
    """Compute PR throughput metrics using gh CLI.

    Returns a formatted string like:
        PR throughput: 3 open, 5 merged (last 7d), avg merge time: 2.3h
    Returns None if gh fails or no PR data available.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list", "--author", "@me", "--state", "all",
                "--json", "number,state,createdAt,mergedAt", "--limit", "20",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        prs = json.loads(result.stdout)
        if not prs:
            return None
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        return None

    open_count = sum(1 for pr in prs if pr.get("state") == "OPEN")
    now = datetime.now(timezone.utc)
    seven_days_ago = now.timestamp() - 7 * 86400

    merged_recent = []
    for pr in prs:
        if pr.get("state") != "MERGED" or not pr.get("mergedAt"):
            continue
        merged_at = datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
        if merged_at.timestamp() >= seven_days_ago:
            created_at = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
            hours = (merged_at - created_at).total_seconds() / 3600
            merged_recent.append(hours)

    merged_count = len(merged_recent)
    if open_count == 0 and merged_count == 0:
        return None

    parts = [f"PR throughput: {open_count} open, {merged_count} merged (last 7d)"]
    if merged_recent:
        avg_hours = sum(merged_recent) / len(merged_recent)
        parts.append(f"avg merge time: {avg_hours:.1f}h")

    return ", ".join(parts)


def get_skill_failure_rates():
    """Cross-reference agent-quality-tracker for skill failure rates.

    Reads ~/.claude/agent-quality-tracker.jsonl and returns skills with >10% failure rate.
    Returns None if file doesn't exist or no notable failure rates.
    """
    tracker_path = QUALITY_TRACKER_PATH
    if not tracker_path.exists():
        return None

    totals = Counter()
    failures = Counter()

    try:
        with open(tracker_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                skill = entry.get("skill")
                if not skill:
                    continue
                totals[skill] += 1
                if entry.get("status") == "error":
                    failures[skill] += 1
    except OSError:
        return None

    notable = []
    for skill in sorted(totals):
        total = totals[skill]
        fail = failures.get(skill, 0)
        if total > 0 and fail / total > 0.10:
            pct = fail / total * 100
            notable.append(f"{skill} {fail}/{total} ({pct:.0f}%)")

    if not notable:
        return None

    return "Skill failure rates: " + ", ".join(notable)


def main():
    records = load_recent_metrics()
    if not records:
        return

    current_session = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    sessions = {}
    for r in records:
        sid = r.get("session", "unknown")
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(r)

    # Session cost summaries
    cost_summaries = summarize_sessions(sessions, current_session)

    # Anomaly detection
    all_anomalies = []
    for sid in sessions:
        if sid == current_session:
            continue
        anomalies = analyze_session(records, sid)
        if anomalies:
            all_anomalies.extend(anomalies)

    # Branch/PR-level aggregation
    branch_data = aggregate_by_branch(records)
    branch_summary = format_branch_summary(branch_data)

    # PR throughput (F12)
    pr_throughput = get_pr_throughput()

    # Skill failure rates (F5)
    skill_failures = get_skill_failure_rates()

    if not cost_summaries and not all_anomalies and not branch_summary and not pr_throughput and not skill_failures:
        return

    parts = []
    if cost_summaries:
        parts.append(
            "Session cost summary (last 3 sessions):\n"
            + "\n".join(cost_summaries)
        )
    if all_anomalies:
        all_anomalies = all_anomalies[:5]
        parts.append(
            "Anomalies:\n" + "\n".join(f"- {a}" for a in all_anomalies)
        )
    if branch_summary:
        parts.append(branch_summary)
    if pr_throughput:
        parts.append(pr_throughput)
    if skill_failures:
        parts.append(skill_failures)
    advisory("\n\n".join(parts))


if __name__ == "__main__":
    main()
