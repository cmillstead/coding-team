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
from _lib.state import get_session_id

HOOKS_DIR = Path.home() / ".claude" / "hooks"
SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
METRICS_DIR = Path.home() / ".claude" / "metrics"
TIMEOUT_SECONDS = 5
MAX_METRICS_FILES = 3
METRICS_STALENESS_DAYS = 7

# Threshold for the AGGREGATE deployed always-loaded surface. Same 200 as the
# per-file instruction check in check_instruction_file_lengths() — beyond
# ~200 lines, MANDATORY labels stop working (case study #24) — but what a
# session actually pays is the TOTAL, and the saturation audit's reduction
# target (163) is sized against 200.
#
# The literal 200 at the per-file check is deliberately NOT replaced with this
# name. That check is a different measurement (per-file, and rooted at
# __file__ rather than at home, so its root moves between the deployed hook
# and the test suite) that
# this work leaves untouched; binding the two to one constant would couple
# them, so a future change to the aggregate threshold would silently move the
# per-file cap too. Two independent 200s is the correct shape here.
ALWAYS_LOADED_THRESHOLD = 200


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

    # Interpreters whose second token is expected to be a script file path.
    _SCRIPT_INTERPRETERS = {"python", "python3", "bash", "sh", "node"}

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

                # F2 fix: only treat a token as a hook file path when the interpreter
                # basename is a known script runner AND the candidate token looks like
                # a path (contains "/" or ends in ".py"/".sh"). Commands like
                # "rtk hook claude" do not meet either criterion and are skipped.
                interpreter = Path(parts[0]).name
                if interpreter not in _SCRIPT_INTERPRETERS:
                    continue
                file_str = parts[-1]
                if "/" not in file_str and not (
                    file_str.endswith(".py") or file_str.endswith(".sh")
                ):
                    continue

                # F3 fix: use the expanduser()'d (but NOT resolve()'d) path for the
                # HOOKS_DIR membership check. This keeps symlinks written as
                # ~/.claude/hooks/... classified as INTERNAL even when their resolved
                # targets live outside HOOKS_DIR (e.g. in skills/coding-team/hooks/).
                expanded_path = Path(file_str).expanduser()
                try:
                    expanded_path.relative_to(HOOKS_DIR)
                    continue  # Inside HOOKS_DIR, skip
                except ValueError:
                    pass  # Outside HOOKS_DIR, include

                # Resolve only after the membership check (for dedup and existence checks).
                file_path = expanded_path.resolve()
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


def check_instruction_file_lengths(repo_root: Path | None = None) -> list[str]:
    """Check that instruction files (agents, phases, skills) are under 200 lines.

    Case study #24: beyond ~200 lines, MANDATORY labels stop working.
    Files over 200 lines should be split or have content extracted to on-demand files.

    `repo_root` defaults to `Path(__file__).parent.parent`, which resolves
    DIFFERENTLY in the two contexts this runs in — and that divergence is why the
    nested globs below exist:

      - under pytest, `__file__` is this repo's `hooks/`, so the root is THIS repo
        and the flat `agents/*.md` / `phases/*.md` patterns match;
      - in production the deployed hook is invoked as
        `~/.claude/hooks/hook-health-check.py` and `__file__` is NOT
        symlink-resolved, so the root is `~/.claude` — which has an `agents/`
        dir (symlinks into this repo, which is why ct-implementer.md was
        reported) but NO `phases/` dir at all. The flat `phases/*.md` pattern
        therefore matched NOTHING in production, and every phase file went
        unchecked. Three were over threshold when this was found.

    The nested `skills/*/phases/*.md` and `skills/*/agents/*.md` patterns close
    that gap from the `~/.claude` root. They are additive and root-agnostic: under
    the pytest root they match nothing the flat patterns did not already cover, so
    no expectation changes and nothing is double-reported (results are deduped
    below regardless).

    Do NOT "fix" this by switching to `Path.home()`. The sibling
    check_always_loaded_surface() uses Path.home() deliberately because it measures
    the DEPLOYED surface in both contexts; this function measures whichever repo it
    ships inside, and repointing it at ~/.claude would change the file set under
    test — the exact regression that sibling's docstring warns about.
    """
    warnings = []
    if repo_root is None:
        repo_root = Path(__file__).parent.parent

    instruction_globs = [
        "agents/*.md",
        "phases/*.md",
        "skills/*/SKILL.md",
        # Nested: the ~/.claude production root reaches submodule instruction
        # files only through skills/<submodule>/.
        "skills/*/phases/*.md",
        "skills/*/agents/*.md",
    ]

    # Dedupe on the RESOLVED target, not the glob path. ~/.claude/agents/x.md is a
    # symlink to skills/coding-team/agents/x.md, so both patterns yield the same
    # underlying file under two different paths — comparing unresolved paths would
    # report it twice. Falls back to the raw path when resolution fails (broken
    # symlink / ELOOP), which at worst restores the old duplicate rather than
    # dropping a real warning.
    seen: set[Path] = set()
    for pattern in instruction_globs:
        for filepath in repo_root.glob(pattern):
            try:
                key = filepath.resolve()
            except (OSError, ValueError, RuntimeError):
                key = filepath
            if key in seen:
                continue
            seen.add(key)
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


def _read_lines(path: Path) -> int | None:
    """Return the line count of path, or None if it cannot be read at all.

    "Cannot be read" covers absence, a broken symlink, a permission error, and
    a decoding failure alike — all raise inside path.read_text(). Returning
    None (rather than 0) for every one of those cases matters because a
    caller may need to tell "unreadable" apart from "read successfully and
    got zero lines" — collapsing them into the same 0 would make a broken
    symlink indistinguishable from an empty file. check_always_loaded_surface()
    below is exactly such a caller: it needs "present but unreadable" (e.g. a
    broken ~/.claude/CLAUDE.md or ~/.claude/rules/*.md symlink) to be a
    distinct, reportable state rather than silently folded into 0.
    """
    try:
        return len(path.read_text().splitlines())
    except (OSError, UnicodeDecodeError):
        return None


def _measure_file(path: Path) -> tuple[int, str]:
    """Return (line_count, status) for a single always-loaded FILE input.

    status is exactly one of:
      - "measured": read successfully; line_count is meaningful.
      - "absent": genuinely not there (no file, no symlink at all) —
        line_count is 0, and this is NOT a measurement failure.
      - "unreadable": something exists at this path (a file, or a symlink of
        any kind) but it could not be read (broken symlink target,
        permission error, decode failure) — line_count is 0, and this IS a
        measurement failure.

    Used for ~/.claude/CLAUDE.md and for each ~/.claude/rules/*.md entry.
    See check_always_loaded_surface's docstring (design choice 4) for why
    every input goes through a shared three-way discrimination like this one
    instead of each caller reimplementing its own absent/unreadable check.
    """
    lines = _read_lines(path)
    if lines is not None:
        return lines, "measured"
    if path.exists() or path.is_symlink():
        return 0, "unreadable"
    return 0, "absent"


def _measure_rules_dir(rules_dir: Path) -> tuple[list[Path], str]:
    """Return (entries, status) for the ~/.claude/rules/ DIRECTORY input itself.

    status is exactly one of:
      - "measured": rules_dir is a real, traversable directory. entries is
        its sorted *.md children (possibly empty — an empty, readable
        rules/ is legitimately "measured, found nothing").
      - "absent": genuinely not there (no file, no symlink at all) —
        entries is []. NOT a measurement failure.
      - "unreadable": something exists at this path but cannot be
        enumerated as a directory: a broken symlink, a regular file sitting
        where a directory belongs, or a real directory whose contents
        cannot be listed (permission denied). entries is []. THIS is a
        measurement failure, unlike "absent".

    is_dir() alone cannot detect the permission-denied case — it confirms
    the path itself is a directory, not that its contents are readable —
    and Path.glob() silently swallows PermissionError during traversal and
    yields no entries, which is the same "unreadable read as measured-empty"
    defect this function exists to close. Path.iterdir() raises instead of
    swallowing, so traversal happens inside try/except OSError rather than
    being inferred from is_dir() alone.
    """
    if not rules_dir.exists() and not rules_dir.is_symlink():
        return [], "absent"
    if not rules_dir.is_dir():
        return [], "unreadable"
    try:
        entries = sorted(p for p in rules_dir.iterdir() if p.name.endswith(".md"))
    except OSError:
        return [], "unreadable"
    return entries, "measured"


def check_always_loaded_surface(claude_dir: Path | None = None) -> list[str]:
    """Warn when the DEPLOYED always-loaded surface exceeds the line threshold.

    Sums ~/.claude/CLAUDE.md plus every ~/.claude/rules/*.md and compares the
    TOTAL against ALWAYS_LOADED_THRESHOLD. Both load unconditionally into every
    session and every subagent, so the sum is the largest fixed component of
    what a session pays — NOT the total. This project also auto-loads a
    per-project ~/.claude/projects/<slug>/memory/MEMORY.md into every session
    (64 lines today, and it grows every time a feedback memory lands), and
    this check does not measure it. Treat the number this check reports as a
    floor, not a total.

    Four design choices, each load-bearing:

    1. It reads the DEPLOYED directory (~/.claude), NOT this repository.
       ~/.claude is itself a git repo (cmillstead/claude-harness) that tracks
       rules/ in place, and skills/coding-team is a SUBMODULE of it. So
       ~/.claude/rules/ has TWO owners: symlinks deployed from this repo and
       regular files owned by the parent. Reading the deployed directory spans
       both owners by construction, which is precisely why the ownership
       question does not need resolving for the measurement to be correct.
       Path.home() is used deliberately instead of the __file__-relative root
       that check_instruction_file_lengths() above uses. That one derives
       `repo_root = Path(__file__).parent.parent`, and __file__ is NOT
       symlink-resolved — the deployed hook is invoked as
       ~/.claude/hooks/hook-health-check.py, so that root is ~/.claude in
       production but this repo under pytest. Path.home() is the same in both.
       Do NOT "simplify" this to a repo_root.glob(): under the test suite that
       root matches this repo's rules/*.md — 3 files, 61 lines, one of which
       (README.md) is not deployed and not always-loaded at all. So the
       regression would ship green while measuring a partly different FILE SET
       from the one production reads, at a number that depends on how the
       module was loaded.

    2. It is an AGGREGATE, not a per-file cap. Individual rules files run 5-29
       lines, so no per-file threshold would ever fire on them. The SUM is the
       defect. Do NOT convert this to a per-file check.

    3. It is ADVISORY ONLY and never blocks. It returns warning strings that
       main() folds into the SessionStart advisory emitted via
       allow_with_reason(). It is expected to fire on every session until the
       surface-reduction phases land — that visibility is the entire point. Do
       NOT raise the threshold, suppress the warning, or add an exemption to
       stop it firing. A separate, later change (audit finding F2) adds a
       BLOCKING per-file cap in write-guard.py; that one must land only after
       the reductions, because a blocking cap would block the very edits that
       reduce the surface. This warning carries no such ordering hazard.

    4. EVERY always-loaded input this check reads — ~/.claude/CLAUDE.md, the
       ~/.claude/rules/ DIRECTORY itself, and each individual rules/*.md
       entry — is routed through the same affirmative three-way
       discrimination (_measure_file() for files, _measure_rules_dir() for
       the directory): "measured" (read/listed successfully), "absent"
       (genuinely not there at all — not a failure), or "unreadable"
       (present but could not be measured — IS a failure). Every input's
       status is collected into one `statuses` list, and
       `measurement_incomplete = any(status == "unreadable" for status in
       statuses)` is the ENTIRE derivation — no per-input special case, no
       enumerated list of "known" failure modes to keep in sync by hand.
       That flag, not any per-input branch, is what gates the early return
       (`if total <= ALWAYS_LOADED_THRESHOLD and not measurement_incomplete`).

       This shape exists because the alternative — enumerating known failure
       modes one at a time — kept missing one. Three separate review passes
       found three separate instances of the identical class, each entering
       through a different input this check reads: an unreadable CLAUDE.md
       file, an unreadable rules/*.md entry, and an unmeasurable rules/
       directory itself (broken symlink, a regular file where a directory
       belongs, or a real directory whose contents raise OSError on
       listing — is_dir() alone cannot see that last one, and glob()
       silently swallows PermissionError rather than surfacing it). Each
       time, the surviving total fell to or under ALWAYS_LOADED_THRESHOLD
       and the check went dark, because "could not measure" had silently
       become "measured, found nothing" for exactly the one input not yet
       covered. Routing every input through an affirmative measured/
       absent/unreadable discrimination — rather than patching each newly
       discovered failure mode into the gate condition — means a future
       fourth input is added to the `statuses` enumeration, with
       measurement_incomplete following automatically; it cannot recreate
       this class by being forgotten as a new conjunct. A rules/*.md entry
       specifically is ALSO excluded from the measured line count and the
       reported file count when unreadable (never silently counted as 0
       lines against a file count that includes it) and is named via the
       "(N unreadable)" fragment in the warning text.

    5. ~/.claude/CLAUDE.md is a deploy symlink (-> skills/coding-team/
       config/CLAUDE.md) exactly like a rules/ entry, and carries 238 of the
       354 currently-deployed lines, so its unreadability is one of the
       largest things measurement_incomplete (design choice 4) can catch —
       alongside the rules/ directory itself going unreadable, which can
       silently drop the entire rules/ side to 0 the same way. Genuine
       ABSENCE (no file and no symlink at all, for either CLAUDE.md or
       rules/) is NOT unreadable and stays silent under threshold — see
       below. _measure_file() and _measure_rules_dir() both keep "absent"
       distinct from "unreadable" by checking exists()/is_symlink() rather
       than inferring absence from a None line count alone, which is what
       let a broken symlink masquerade as absence in the original defect.

    Degrades silently ONLY when ~/.claude/CLAUDE.md is genuinely ABSENT (no
    file, no symlink) or ~/.claude/rules/ is absent (a machine that deploys
    neither): missing inputs mean there is nothing to measure, not a problem
    to report. Returns [] in that case. Whenever measurement_incomplete is
    True (design choice 4) — ANY measured input's status is "unreadable" —
    the check always surfaces, even when the surviving total is under
    threshold. The function itself does not otherwise raise, though
    Path.home() can raise RuntimeError if HOME is unset and there is no
    passwd entry for the current user — this function does not guard
    against that.

    Args:
        claude_dir: Root to measure. Defaults to ~/.claude. Tests pass a real
            temporary directory; production passes nothing.
    """
    if claude_dir is None:
        claude_dir = Path.home() / ".claude"

    claude_md = claude_dir / "CLAUDE.md"
    rules_dir = claude_dir / "rules"

    claude_md_lines, claude_md_status = _measure_file(claude_md)
    rules_entries, rules_dir_status = _measure_rules_dir(rules_dir)

    # Every input's status lands in ONE list. measurement_incomplete is the
    # entire derivation — see design choice 4 for why a fourth input only
    # needs its status appended here, nothing more.
    statuses = [claude_md_status, rules_dir_status]

    rules_files = []
    rules_lines = 0
    unreadable = 0
    for entry in rules_entries:
        lines, status = _measure_file(entry)
        statuses.append(status)
        if status == "measured":
            rules_files.append(entry)
            rules_lines += lines
        else:
            # Entries come from _measure_rules_dir()'s iterdir(), so each one
            # is a real directory entry that exists — "absent" cannot occur
            # here, only "unreadable" (e.g. a broken per-entry symlink).
            unreadable += 1

    total = claude_md_lines + rules_lines
    measurement_incomplete = any(status == "unreadable" for status in statuses)
    if total <= ALWAYS_LOADED_THRESHOLD and not measurement_incomplete:
        return []

    unreadable_fragment = f" ({unreadable} unreadable)" if unreadable else ""

    if claude_md_status == "unreadable":
        claude_md_fragment = (
            f"{claude_md}: UNREADABLE (broken symlink, permission error, or "
            "decode failure) — excluded from the total below, so the "
            "reported total is INCOMPLETE, not a true total"
        )
    else:
        claude_md_fragment = f"{claude_md}: {claude_md_lines} lines"

    if rules_dir_status == "unreadable":
        rules_fragment = (
            f"{rules_dir}/*.md: UNREADABLE (broken symlink, not a directory, "
            "or permission denied) — could not be listed, so the reported "
            "total is INCOMPLETE, not a true total"
        )
    else:
        rules_fragment = (
            f"{rules_dir}/*.md: {rules_lines} lines across "
            f"{len(rules_files)} file(s){unreadable_fragment}"
        )

    incomplete_note = (
        " At least one always-loaded input above could not be measured, so "
        "this total is INCOMPLETE — treat it as a floor, not the true total."
        if measurement_incomplete
        else ""
    )

    return [
        f"Always-loaded surface is {total} lines "
        f"(threshold: {ALWAYS_LOADED_THRESHOLD}). "
        f"{claude_md_fragment}. "
        f"{rules_fragment}."
        f"{incomplete_note} "
        "Both load into every session and every subagent — reduce whichever "
        "side is larger."
    ]


def check_mcp_health() -> list[str]:
    """Probe configured MCP servers for availability.

    Checks whether the codesight-mcp binary is reachable via PATH or common
    install locations. Returns a list of warning strings for any servers that
    cannot be found.
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
    cutoff = datetime.now().timestamp() - (METRICS_STALENESS_DAYS * 86400)
    files = [f for f in files if f.stat().st_mtime >= cutoff]
    if not files:
        return []
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


_PR_THROUGHPUT_CACHE_TTL = 3600  # seconds


def get_pr_throughput():
    """Compute PR throughput metrics using gh CLI, cached for 1 hour.

    Returns a formatted string or None if gh fails or no PR data available.
    Reads from a cache file if it is < 1h old to keep SessionStart non-blocking.
    """
    import time

    cache_file = METRICS_DIR / ".pr-throughput-cache.json"

    # Return cached value if fresh (< TTL seconds old)
    if cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text())
            if time.time() - cached["ts"] < _PR_THROUGHPUT_CACHE_TTL:
                return cached["value"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass  # Corrupt or unreadable cache — fall through to gh

    try:
        result = subprocess.run(
            [
                "gh", "pr", "list", "--author", "@me", "--state", "all",
                "--json", "number,state,createdAt,mergedAt", "--limit", "20",
            ],
            capture_output=True,
            text=True,
            timeout=3,
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

    value = ", ".join(parts)

    # Write cache — best-effort, do not fail if METRICS_DIR does not exist
    try:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"value": value, "ts": time.time()}))
    except OSError:
        pass

    return value


def get_skill_failure_rates():
    """Cross-reference agent-quality-tracker for skill failure rates.

    Returns skills with >10% failure rate, or None if no data.
    """
    if not METRICS_DIR.exists():
        return None

    files = sorted(METRICS_DIR.glob("agent-quality-*.jsonl"), reverse=True)
    cutoff = datetime.now().timestamp() - (METRICS_STALENESS_DAYS * 86400)
    files = [f for f in files if f.stat().st_mtime >= cutoff]
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

    current_session = get_session_id()

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
    # Dispatchers fan out to other hooks (each owns its own subprocess +
    # timeout), so probing them here either recurses (hook-health-check) or
    # times out spuriously (session-start-dispatcher spawns all six checks,
    # blowing the 5s structural-probe budget). Their constituents are probed
    # individually, so skipping the dispatchers loses no coverage.
    _SKIP_PROBE = {
        "hook-health-check.py",
        "session-start-dispatcher.py",
        "prompt-dispatcher.py",
    }
    for hook_path in sorted(HOOKS_DIR.glob("*.py")):
        if hook_path.name in _SKIP_PROBE:
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

    # Check the DEPLOYED always-loaded surface as an aggregate (F1). Separate
    # from the per-file check above for two reasons: that one's glob list has
    # no entry for CLAUDE.md or rules/*.md, and its __file__-relative root
    # differs between the deployed hook and the test suite. This one is
    # home-relative and aggregate.
    surface_warnings = check_always_loaded_surface()

    # Check skill symlinks (merged from symlink-integrity-check.py)
    symlink_issues = check_skill_symlinks()

    # Analyze session metrics (merged from metrics-analyzer.py)
    metrics_parts = check_metrics()

    if (not unhealthy and not mcp_issues and not length_warnings
            and not symlink_issues and not metrics_parts
            and not surface_warnings):
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
    if surface_warnings:
        parts.append(
            "Always-loaded surface check:\n"
            + "\n".join(f"  - {w}" for w in surface_warnings)
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
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — advisory hook: fail open, never break the session
        print(f"hook-health-check.py: crashed with {exc!r} — advisory hook, continuing", file=sys.stderr)
    sys.exit(0)
