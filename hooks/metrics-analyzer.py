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

    return anomalies


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

    all_anomalies = []
    for sid in sessions:
        if sid == current_session:
            continue
        anomalies = analyze_session(records, sid)
        if anomalies:
            all_anomalies.extend(anomalies)

    if not all_anomalies:
        return

    all_anomalies = all_anomalies[:5]
    msg = "Metrics review from recent sessions:\n" + "\n".join(
        f"- {a}" for a in all_anomalies
    )
    print(json.dumps({"decision": "allow", "reason": msg}))


if __name__ == "__main__":
    main()
