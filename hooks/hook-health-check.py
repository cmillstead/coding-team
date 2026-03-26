#!/usr/bin/env python3
"""Claude Code SessionStart hook: verify hooks are healthy and analyze metrics.

Two responsibilities merged into one SessionStart hook:
1. Structural health checks — runs each Python/shell hook with empty input,
   reports crashes, syntax errors, or timeouts. A broken hook silently degrades
   to no protection; this makes that degradation visible.
2. Metrics analysis — reads JSONL files from ~/.claude/metrics/, computes
   aggregate statistics for recent sessions, and surfaces anomalies:
   - High Edit:Read ratio (>3:1) suggests stale context
   - Excessive Bash calls (>30) suggests retry loops
   - Long sessions (200+ tool calls) need compaction
   - Low search usage — many edits with no Grep/Glob

Does NOT block the session — all output is advisory.
"""
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib.output import allow_with_reason

HOOKS_DIR = Path.home() / ".claude" / "hooks"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
METRICS_DIR = Path.home() / ".claude" / "metrics"
TIMEOUT_SECONDS = 5
MAX_METRICS_FILES = 3


def check_hook(hook_path: Path) -> str | None:
    """Run a hook with empty JSON input and check for crashes.

    Returns an error message string if the hook is unhealthy, None if OK.
    """
    try:
        result = subprocess.run(
            [sys.executable, str(hook_path)],
            input='{}',
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        # Exit code 0 or 1 are both acceptable (hook may reject empty input)
        # Exit code 2+ or stderr with "Error"/"Traceback" indicates a problem
        if result.returncode > 1:
            stderr_snippet = result.stderr.strip()[:200] if result.stderr else "no stderr"
            return f"exit code {result.returncode}: {stderr_snippet}"
        if result.stderr and ("Traceback" in result.stderr or "SyntaxError" in result.stderr):
            stderr_snippet = result.stderr.strip()[:200]
            return f"stderr: {stderr_snippet}"
        return None
    except subprocess.TimeoutExpired:
        return f"timeout after {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return "python3 not found"
    except OSError as e:
        return f"OSError: {e}"


def check_sh_hook(hook_path: Path) -> str | None:
    """Run bash -n on a shell hook to check for syntax errors.

    Returns an error message string if the hook is unhealthy, None if OK.
    """
    try:
        result = subprocess.run(
            ["bash", "-n", str(hook_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            stderr_snippet = result.stderr.strip()[:200] if result.stderr else "syntax error"
            return f"bash syntax error: {stderr_snippet}"
        return None
    except subprocess.TimeoutExpired:
        return f"timeout after {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return "bash not found"
    except OSError as e:
        return f"OSError: {e}"


def get_external_hook_paths() -> list[Path]:
    """Extract hook file paths from settings.json that are outside ~/.claude/hooks/.

    Parses all hook entries across SessionStart, PreToolUse, PostToolUse and
    extracts command paths. Returns unique paths that are NOT inside HOOKS_DIR
    (those are already checked by the main loop).
    """
    if not SETTINGS_PATH.is_file():
        return []

    try:
        settings = json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    hooks_config = settings.get("hooks", {})
    seen = set()
    external_paths = []

    for event_type in ("SessionStart", "PreToolUse", "PostToolUse"):
        for matcher_block in hooks_config.get(event_type, []):
            for hook_entry in matcher_block.get("hooks", []):
                command = hook_entry.get("command", "")
                if not command:
                    continue
                # Extract the file path from commands like "python3 ~/.config/foo.py"
                # or "bash ~/.claude/hooks/bar.sh"
                parts = command.split()
                if len(parts) < 2:
                    continue
                # The file path is typically the last argument
                file_str = parts[-1]
                # Expand ~ to home directory
                file_path = Path(file_str).expanduser().resolve()
                # Skip paths inside HOOKS_DIR (already checked by main loop)
                try:
                    file_path.relative_to(HOOKS_DIR.resolve())
                    continue  # Inside HOOKS_DIR, skip
                except ValueError:
                    pass  # Outside HOOKS_DIR, include
                if file_path not in seen:
                    seen.add(file_path)
                    external_paths.append(file_path)

    return external_paths


def check_external_hook(hook_path: Path) -> str | None:
    """Check an external hook file for health.

    Returns an error message if unhealthy, None if OK.
    Delegates to check_hook() for .py files and check_sh_hook() for .sh files.
    """
    if not hook_path.is_file():
        return "file not found"

    suffix = hook_path.suffix.lower()
    if suffix == ".py":
        return check_hook(hook_path)
    elif suffix == ".sh":
        return check_sh_hook(hook_path)
    else:
        return None  # Unknown type, skip silently


def check_instruction_file_lengths() -> list[str]:
    """Check that instruction files (agents, phases, skills) are under 200 lines.

    Case study #24: beyond ~200 lines, MANDATORY labels stop working.
    Files over 200 lines should be split or have content extracted to on-demand files.
    """
    warnings = []
    repo_root = Path(__file__).parent.parent

    instruction_globs = [
        "agents/*.md",
        "phases/*.md",
        "skills/*/SKILL.md",
    ]

    for pattern in instruction_globs:
        for filepath in repo_root.glob(pattern):
            try:
                line_count = len(filepath.read_text().splitlines())
                if line_count > 200:
                    warnings.append(
                        f"{filepath.relative_to(repo_root)} is {line_count} lines "
                        f"(threshold: 200). Consider extracting content to on-demand files."
                    )
            except OSError:
                continue

    return warnings


def check_mcp_health() -> list[str]:
    """Probe configured MCP servers for availability.

    Checks whether codesight-mcp and qmd binaries are reachable via PATH
    or common install locations. Returns a list of warning strings for
    any servers that cannot be found.
    """
    issues = []

    # Check codesight-mcp binary availability
    if not shutil.which("codesight-mcp"):
        common_paths = [
            Path.home() / ".local" / "bin" / "codesight-mcp",
            Path("/usr/local/bin/codesight-mcp"),
        ]
        if not any(p.exists() for p in common_paths):
            issues.append("codesight-mcp binary not found in PATH or common locations")

    # Check qmd binary availability
    if not shutil.which("qmd"):
        common_paths = [
            Path("/opt/homebrew/bin/qmd"),
            Path("/usr/local/bin/qmd"),
        ]
        if not any(p.exists() for p in common_paths):
            issues.append("qmd binary not found in PATH or common locations")

    return issues


def check_skill_symlinks() -> list[str]:
    """Check that symlinks in ~/.claude/skills/ are not broken.

    Returns a list of warning strings for broken symlinks.
    """
    skills_dir = Path.home() / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    broken = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_symlink() and not entry.resolve().exists():
            broken.append(f"Broken symlink: {entry.name} -> {os.readlink(entry)}")
    return broken


def load_recent_metrics():
    """Load records from the most recent JSONL metrics files."""
    if not METRICS_DIR.exists():
        return []
    files = sorted(METRICS_DIR.glob("tool-usage-*.jsonl"), reverse=True)
    records = []
    for f in files[:MAX_METRICS_FILES]:
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
    """Detect anomalies in a single session's tool usage."""
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
        anomalies.append(
            f"{edits} Edit calls with 0 Read calls — always read before editing"
        )

    bash_count = tool_counts.get("Bash", 0)
    if bash_count > 30:
        anomalies.append(
            f"{bash_count} Bash calls in session — likely retry loop. "
            "Use alternative approaches instead of re-running the same command."
        )

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

    agent_calls = tool_counts.get("Agent", 0)
    if total > 0 and agent_calls / total > 0.4:
        pct = agent_calls / total * 100
        anomalies.append(
            f"High agent dispatch ratio ({agent_calls}/{total} = {pct:.0f}%)"
            " — consider consolidating worker prompts"
        )

    return anomalies


def summarize_sessions(sessions, current_session, max_sessions=3):
    """Compute per-session cost summary: total calls, top tools, skills."""
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

    Returns a dict mapping branch name to total_calls, session_count,
    top_tools, and sessions. Only branches with 2+ sessions are included.
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
    """Format branch aggregation data into a human-readable string."""
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

    Returns a formatted string or None if gh fails or no PR data available.
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
    except (subprocess.TimeoutExpired, subprocess.SubprocessError,
            json.JSONDecodeError, FileNotFoundError):
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
            created_at = datetime.fromisoformat(
                pr["createdAt"].replace("Z", "+00:00")
            )
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

    Returns skills with >10% failure rate, or None if no data.
    """
    if not METRICS_DIR.exists():
        return None

    files = sorted(METRICS_DIR.glob("agent-quality-*.jsonl"), reverse=True)
    if not files:
        return None

    totals = Counter()
    failures = Counter()

    for f in files[:MAX_METRICS_FILES]:
        try:
            with open(f) as fh:
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
            continue

    if not totals:
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


def check_metrics():
    """Analyze recent session metrics for anomalies and cost summaries.

    Returns a list of formatted strings. Returns empty list if no metrics exist.
    """
    records = load_recent_metrics()
    if not records:
        return []

    current_session = os.environ.get("CLAUDE_SESSION_ID", "unknown")

    sessions = {}
    for r in records:
        sid = r.get("session", "unknown")
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(r)

    cost_summaries = summarize_sessions(sessions, current_session)

    all_anomalies = []
    for sid in sessions:
        if sid == current_session:
            continue
        anomalies = analyze_session(records, sid)
        if anomalies:
            all_anomalies.extend(anomalies)

    branch_data = aggregate_by_branch(records)
    branch_summary = format_branch_summary(branch_data)
    pr_throughput = get_pr_throughput()
    skill_failures = get_skill_failure_rates()

    if (not cost_summaries and not all_anomalies and not branch_summary
            and not pr_throughput and not skill_failures):
        return []

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
    return parts


def main():
    if not HOOKS_DIR.is_dir():
        return

    unhealthy = []
    for hook_path in sorted(HOOKS_DIR.glob("*.py")):
        # Skip self to avoid recursion
        if hook_path.name == "hook-health-check.py":
            continue
        error = check_hook(hook_path)
        if error:
            unhealthy.append(f"  - {hook_path.name}: {error}")

    for hook_path in sorted(HOOKS_DIR.glob("*.sh")):
        error = check_sh_hook(hook_path)
        if error:
            unhealthy.append(f"  - {hook_path.name}: {error}")

    # Check external hooks registered in settings.json
    for ext_path in get_external_hook_paths():
        error = check_external_hook(ext_path)
        if error:
            unhealthy.append(f"  - [external] {ext_path}: {error}")

    # Check MCP server availability (advisory warnings, not blockers)
    mcp_issues = check_mcp_health()

    # Check instruction file lengths (case study #24: context saturation)
    length_warnings = check_instruction_file_lengths()

    # Check skill symlinks (merged from symlink-integrity-check.py)
    symlink_issues = check_skill_symlinks()

    # Analyze session metrics (merged from metrics-analyzer.py)
    metrics_parts = check_metrics()

    if (not unhealthy and not mcp_issues and not length_warnings
            and not symlink_issues and not metrics_parts):
        return  # All healthy, no metrics — silent success

    parts = []
    if unhealthy:
        parts.append(
            f"Hook health check: {len(unhealthy)} unhealthy hook(s) detected.\n"
            "These hooks may silently fail to protect you:\n"
            + "\n".join(unhealthy)
            + "\n\nFix or remove broken hooks to restore protection."
        )
    if mcp_issues:
        parts.append(
            f"MCP health check: {len(mcp_issues)} server(s) unavailable.\n"
            "Agents will waste tool calls discovering this at first use:\n"
            + "\n".join(f"  - {issue}" for issue in mcp_issues)
        )
    if length_warnings:
        parts.append(
            f"Instruction file length check: {len(length_warnings)} file(s) over 200 lines.\n"
            "Context saturation degrades compliance beyond ~200 lines:\n"
            + "\n".join(f"  - {w}" for w in length_warnings)
        )
    if symlink_issues:
        parts.append(
            f"Skill symlink check: {len(symlink_issues)} broken symlink(s).\n"
            + "\n".join(f"  - {s}" for s in symlink_issues)
            + "\n\nFix with: ln -sf <repo-skill-dir> ~/.claude/skills/<name>"
        )
    if metrics_parts:
        parts.extend(metrics_parts)

    msg = "\n\n".join(parts)
    allow_with_reason(msg)


if __name__ == "__main__":
    main()
