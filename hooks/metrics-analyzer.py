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
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from _lib.output import advisory

METRICS_DIR = Path.home() / ".claude" / "metrics"
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

    if not cost_summaries and not all_anomalies:
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
    advisory("\n\n".join(parts))


if __name__ == "__main__":
    main()
