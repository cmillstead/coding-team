# Harness Audit Fixes Implementation Plan

**Input findings: 12**

**Goal:** Fix all 12 harness audit findings — 5 new hooks, 3 new rules, 1 project CLAUDE.md, 2 hook enhancements, 1 rule extension. All changes follow existing patterns and register in settings.json.

**Architecture:** Python hooks use JSON stdin/stdout protocol. Rules are markdown with frontmatter globs. All hooks must exit 0 and produce valid JSON (or no output). Hooks are tracked both at `~/.claude/hooks/` (deployed) and `hooks/` in repo.

---

## Context Brief

- **Environment:** `~/.claude/` — user's global Claude Code configuration. Changes affect all sessions.
- **Sacred paths:** `~/.claude/settings.json` — single source of truth for hook registration. Must be valid JSON after every edit.
- **Known landmines:** Hooks that produce invalid JSON or non-zero exit codes break all tool calls. Always exit 0 and output valid JSON.
- **Repo root:** `/Users/cevin/.claude/skills/coding-team`
- **Deploy paths:** Hooks → `~/.claude/hooks/`, Rules → `~/.claude/rules/`, Repo copies → `hooks/` in repo root

---

## Eval Criteria

- [ ] When fixing a behavioral rule in one agent prompt, grep ALL other agent prompts for the same gap before reporting DONE
- [ ] When extracting content from a parent file to a child file, verify the child has a navigation preamble and return instruction
- [ ] All 12 findings accounted for in traceability table
- [ ] All new hooks tested with `echo '...' | python3 hook.py` before marking done
- [ ] settings.json remains valid JSON after all edits

---

## File Structure

| File | Action | Finding | Purpose |
|------|--------|---------|---------|
| `~/.claude/hooks/loop-detection.py` | Modify | F1 | Add behavioral correction with alternative strategies |
| `~/.claude/hooks/metrics-analyzer.py` | Create | F2 | SessionStart hook — surface anomalies from JSONL metrics |
| `~/.claude/hooks/track-artifacts-in-repo.py` | Create | F3a | PostToolUse hook — remind to commit agent/hook files to repo |
| `~/.claude/rules/dark-features.md` | Create | F3b | Rule for reachability checks on implemented features |
| `~/.claude/rules/precomputation.md` | Create | F3c | Rule for pre-computing external data before dispatching |
| `~/.claude/rules/chunk-taxonomy-work.md` | Create | F3d | Rule for chunking large analysis tasks |
| `~/.claude/rules/skill-files.md` | Modify | F3e | Add identity + named rationalizations guidance |
| `/Users/cevin/.claude/projects/-Users-cevin--claude-skills-coding-team/CLAUDE.md` | Create | F4 | Project-level CLAUDE.md for coding-team repo |
| `~/.claude/hooks/context-budget-warning.py` | Modify | F6 | Add token count heuristic from metrics-logger data |
| `~/.claude/hooks/agent-quality-tracker.py` | Create | F7 | PostToolUse Skill hook — log agent outcome signals |
| `~/.claude/hooks/coding-team-active.py` | Modify | F8 | Dynamic skill matching instead of hardcoded set |
| `~/.claude/hooks/identity-framing-check.py` | Create | F9 | PreToolUse Write hook — validate identity preamble |
| `~/.claude/settings.json` | Modify | F2,F3a,F7,F9 | Register 4 new hooks |
| Repo `hooks/` copies | Create/Modify | All hooks | Track in repo alongside deployed versions |

---

## Task 1: Enhance loop-detection.py with Behavioral Correction (F1)

**Files:**
- Modify: `~/.claude/hooks/loop-detection.py` + repo copy `hooks/loop-detection.py`

**Model:** sonnet

### Step 1: Add failure-pattern classification and alternative strategies

Enhance the doom loop message to classify the failure pattern and inject concrete alternative approaches. Replace the generic "stop retrying" message with pattern-specific recovery prompts.

```python
#!/usr/bin/env python3
"""Claude Code PostToolUse hook: detect doom loops and inject recovery strategies.

Monitors repeated Bash failures for the same command pattern. After MAX_RETRIES
failures of the same pattern within 5 minutes, injects structured recovery
prompts with alternative strategies based on the failure type.

Failure categories and recovery strategies:
- Build/compile errors → check dependencies, read error output carefully, try minimal reproduction
- Test failures → run single test, check fixtures, read assertion diff
- Permission/path errors → verify paths exist, check permissions, use absolute paths
- Network errors → check connectivity, verify URLs, try offline alternatives
- Unknown → describe goal, list approaches, identify root cause, ask user
"""
import hashlib
import json
import os
import sys
import time

MAX_RETRIES = 3
STATE_DIR = "/tmp"
STALE_SECONDS = 3600

FAILURE_PATTERNS = {
    "build": {
        "markers": ["cannot find module", "module not found", "no such file or directory",
                     "compilation failed", "build failed", "syntax error", "import error",
                     "modulenotfounderror", "npm err", "cargo error", "tsc error"],
        "strategies": [
            "1. Read the FULL error output — do not skim",
            "2. Check if dependencies are installed: review package.json/pyproject.toml/Cargo.toml",
            "3. Verify import paths are correct relative to the project root",
            "4. Try a minimal reproduction: isolate the failing module",
            "5. Check if the file you're importing actually exists at the expected path",
        ],
    },
    "test": {
        "markers": ["assert", "expected", "actual", "test failed", "pytest", "jest",
                     "mocha", "unittest", "failures=", "errors=", "fail"],
        "strategies": [
            "1. Run the SINGLE failing test in isolation, not the full suite",
            "2. Read the assertion diff carefully — what was expected vs actual?",
            "3. Check test fixtures and setup — is the test environment correct?",
            "4. Add debug logging BEFORE the assertion to inspect intermediate state",
            "5. If the test tests YOUR change, verify the change logic, not the test",
        ],
    },
    "permission": {
        "markers": ["permission denied", "eacces", "operation not permitted",
                     "read-only file system", "not writable"],
        "strategies": [
            "1. Verify the target path exists: use ls -la on the parent directory",
            "2. Use absolute paths — relative paths may resolve unexpectedly",
            "3. Check if you're writing to a read-only location (/usr, /System, etc.)",
            "4. Try a different output location (e.g., /tmp/ for temporary files)",
            "5. Ask the user if elevated permissions are needed",
        ],
    },
    "network": {
        "markers": ["connection refused", "timeout", "econnrefused", "enotfound",
                     "network unreachable", "could not resolve", "ssl", "certificate"],
        "strategies": [
            "1. Verify the URL/endpoint is correct — typos are common",
            "2. Check if the service is running (for local services)",
            "3. Try an offline alternative if available",
            "4. If SSL error, check certificate validity",
            "5. Ask the user about network/proxy configuration",
        ],
    },
}


def get_state_file():
    session_id = os.environ.get("CLAUDE_SESSION_ID", os.environ.get("SESSION_ID", "default"))
    h = hashlib.sha256(session_id.encode()).hexdigest()[:12]
    return os.path.join(STATE_DIR, f"claude-loop-detection-{h}.json")


def load_state(path):
    try:
        with open(path) as f:
            state = json.load(f)
        if time.time() - state.get("last_updated", 0) > STALE_SECONDS:
            return {"failures": [], "last_updated": time.time()}
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return {"failures": [], "last_updated": time.time()}


def save_state(path, state):
    state["last_updated"] = time.time()
    with open(path, "w") as f:
        json.dump(state, f)


def normalize_command(cmd):
    parts = cmd.strip().split()
    if not parts:
        return cmd
    normalized = []
    for part in parts[:5]:
        if "/" in part and not part.startswith("-"):
            normalized.append(os.path.basename(part))
        else:
            normalized.append(part)
    return " ".join(normalized)


def classify_failure(stdout, stderr):
    """Classify failure type based on output content. Returns category key or 'unknown'."""
    combined = (stdout + " " + stderr).lower()
    for category, info in FAILURE_PATTERNS.items():
        for marker in info["markers"]:
            if marker in combined:
                return category
    return "unknown"


def build_recovery_message(pattern, count, category):
    """Build a structured recovery message with category-specific strategies."""
    header = (
        f"DOOM LOOP DETECTED: '{pattern}' failed {count} times in 5 minutes.\n\n"
        f"STOP RETRYING the same approach."
    )

    if category != "unknown" and category in FAILURE_PATTERNS:
        label = category.upper()
        strategies = "\n".join(FAILURE_PATTERNS[category]["strategies"])
        return (
            f"{header}\n\n"
            f"Failure type: {label}\n\n"
            f"Try these alternatives:\n{strategies}\n\n"
            f"If none of these work after 1 attempt each, ask the user for guidance."
        )

    return (
        f"{header}\n\n"
        f"Failure type: UNKNOWN\n\n"
        f"Recovery steps:\n"
        f"1. Describe what you were trying to achieve (the GOAL, not the command)\n"
        f"2. List the {count} approaches you already tried\n"
        f"3. Identify what changed between working and broken state\n"
        f"4. Try ONE different approach (different tool, different path, different method)\n"
        f"5. If that fails too, ask the user for guidance — do not guess further"
    )


def main():
    event = json.load(sys.stdin)
    tool_name = event.get("tool_name", "")

    if tool_name != "Bash":
        return

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})

    command = tool_input.get("command", "")
    if not command:
        return

    stdout = tool_result.get("stdout", "") if isinstance(tool_result, dict) else str(tool_result)
    stderr = tool_result.get("stderr", "") if isinstance(tool_result, dict) else ""
    exit_code = tool_result.get("exit_code", 0) if isinstance(tool_result, dict) else None

    is_failure = False
    if exit_code is not None and exit_code != 0:
        is_failure = True
    elif any(marker in stdout.lower() for marker in ["error", "failed", "failure", "exception", "traceback"]):
        is_failure = True
    elif any(marker in stderr.lower() for marker in ["error", "failed", "failure"]):
        is_failure = True

    state_file = get_state_file()
    state = load_state(state_file)

    if is_failure:
        pattern = normalize_command(command)
        category = classify_failure(stdout, stderr)

        state["failures"].append({
            "pattern": pattern,
            "command": command[:200],
            "category": category,
            "time": time.time(),
        })
        state["failures"] = state["failures"][-20:]
        save_state(state_file, state)

        recent = [f for f in state["failures"]
                  if f["pattern"] == pattern and time.time() - f["time"] < 300]

        if len(recent) >= MAX_RETRIES:
            # Use the most common category from recent failures
            categories = [f.get("category", "unknown") for f in recent]
            dominant = max(set(categories), key=categories.count)
            msg = build_recovery_message(pattern, len(recent), dominant)
            print(json.dumps({"decision": "allow", "reason": msg}))
            return
    else:
        pattern = normalize_command(command)
        state["failures"] = [f for f in state["failures"] if f["pattern"] != pattern]
        save_state(state_file, state)


if __name__ == "__main__":
    main()
```

### Step 2: Verify

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"npm run build"},"tool_result":{"stdout":"module not found: xyz","stderr":"","exit_code":1}}' | python3 ~/.claude/hooks/loop-detection.py
```

Run 3 times to trigger doom loop. Expected: JSON with `build`-category recovery strategies.

### Step 3: Copy to repo

```bash
cp ~/.claude/hooks/loop-detection.py /Users/cevin/.claude/skills/coding-team/hooks/loop-detection.py
```

---

## Task 2: Create metrics-analyzer.py SessionStart Hook (F2)

**Files:**
- Create: `~/.claude/hooks/metrics-analyzer.py` + repo copy
- Modify: `~/.claude/settings.json`

**Model:** sonnet

### Step 1: Create the hook script

SessionStart hook that reads the most recent JSONL file from `~/.claude/metrics/`, computes session-level anomalies, and surfaces them as advisory messages.

```python
#!/usr/bin/env python3
"""Claude Code SessionStart hook: analyze metrics for anomalies.

Reads JSONL files from ~/.claude/metrics/ (written by metrics-logger.py),
computes aggregate statistics for recent sessions, and surfaces anomalies:
- High Edit:Read ratio (>3:1) — editing without reading suggests stale context
- Excessive retries — same Bash command pattern appearing 5+ times
- Long sessions — sessions with 200+ tool calls may need compaction
- Low search usage — large edit sessions with no Grep/Glob calls
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"
MAX_FILES_TO_CHECK = 3  # check today + 2 previous days


def load_recent_metrics():
    """Load metrics from the most recent JSONL files."""
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
    """Analyze a single session's metrics for anomalies."""
    session_records = [r for r in records if r.get("session") == session_id]
    if len(session_records) < 10:
        return []  # too few records to analyze

    anomalies = []
    tool_counts = Counter(r.get("tool", "unknown") for r in session_records)

    # Check Edit:Read ratio
    edits = tool_counts.get("Edit", 0)
    reads = tool_counts.get("Read", 0)
    if edits > 6 and reads > 0 and edits / reads > 3:
        anomalies.append(
            f"High Edit:Read ratio ({edits}:{reads} = {edits/reads:.1f}:1) — "
            f"you may be editing files without re-reading them first"
        )
    elif edits > 3 and reads == 0:
        anomalies.append(
            f"{edits} Edit calls with 0 Read calls — always read before editing"
        )

    # Check for excessive Bash calls (possible retries)
    bash_count = tool_counts.get("Bash", 0)
    if bash_count > 30:
        anomalies.append(
            f"{bash_count} Bash calls in session — check for retry loops"
        )

    # Check session length
    total = len(session_records)
    if total > 200:
        anomalies.append(
            f"{total} tool calls in session — consider compaction to avoid context degradation"
        )

    # Check search usage: if many edits but no search
    searches = tool_counts.get("Grep", 0) + tool_counts.get("Glob", 0)
    if edits > 10 and searches == 0:
        anomalies.append(
            f"{edits} edits with no search calls — use Grep/Glob to verify changes across codebase"
        )

    return anomalies


def main():
    records = load_recent_metrics()
    if not records:
        return  # no metrics data yet

    # Group by session, find the most recent completed session (not current)
    current_session = os.environ.get("CLAUDE_SESSION_ID", "unknown")
    sessions = {}
    for r in records:
        sid = r.get("session", "unknown")
        if sid not in sessions:
            sessions[sid] = []
        sessions[sid].append(r)

    # Analyze previous sessions (not the one just starting)
    all_anomalies = []
    for sid, session_records in sessions.items():
        if sid == current_session:
            continue
        anomalies = analyze_session(records, sid)
        if anomalies:
            all_anomalies.extend(anomalies)

    # Also provide aggregate stats
    if not all_anomalies:
        return  # nothing to report

    # Limit to 5 most relevant anomalies
    all_anomalies = all_anomalies[:5]

    msg = "Metrics review from recent sessions:\n" + "\n".join(f"- {a}" for a in all_anomalies)
    print(json.dumps({"decision": "allow", "reason": msg}))


if __name__ == "__main__":
    main()
```

### Step 2: Register in settings.json

Add to the existing `SessionStart` array:

```json
{
  "type": "command",
  "command": "python3 ~/.claude/hooks/metrics-analyzer.py"
}
```

### Step 3: Verify

```bash
echo '{}' | python3 ~/.claude/hooks/metrics-analyzer.py
```

Expected: No output (no metrics yet) or JSON with anomalies. Must exit 0.

### Step 4: Copy to repo

```bash
cp ~/.claude/hooks/metrics-analyzer.py /Users/cevin/.claude/skills/coding-team/hooks/metrics-analyzer.py
```

---

## Task 3: Create track-artifacts-in-repo.py PostToolUse Hook (F3a)

**Files:**
- Create: `~/.claude/hooks/track-artifacts-in-repo.py` + repo copy
- Modify: `~/.claude/settings.json`

**Model:** sonnet

### Step 1: Create the hook script

PostToolUse hook on `Write|Edit` that checks if the written file is an agent/hook file under `~/.claude/` that should also be tracked in the coding-team repo.

```python
#!/usr/bin/env python3
"""Claude Code PostToolUse hook: remind to commit agent/hook files to team repo.

Fires on Write|Edit. If the target file is under ~/.claude/hooks/ or
~/.claude/agents/ or ~/.claude/skills/, reminds the user to also commit
the file to the coding-team repo at ~/.claude/skills/coding-team/.

Checks if a corresponding file exists in the repo — if not, surfaces a reminder.
"""
import json
import os
import sys
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
REPO_ROOT = CLAUDE_DIR / "skills" / "coding-team"

# Mapping from deployed path prefix to repo subdirectory
TRACKED_DIRS = {
    CLAUDE_DIR / "hooks": REPO_ROOT / "hooks",
    CLAUDE_DIR / "agents": REPO_ROOT / "agents",
}


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return

    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    target = Path(file_path).resolve()

    for deploy_dir, repo_dir in TRACKED_DIRS.items():
        deploy_resolved = deploy_dir.resolve()
        if str(target).startswith(str(deploy_resolved)):
            # File is in a tracked deployed directory
            relative = target.relative_to(deploy_resolved)
            repo_copy = repo_dir / relative

            if not repo_copy.exists():
                msg = (
                    f"New file at {target} — no repo copy found at {repo_copy}.\n"
                    f"Remember to copy this file to the team repo and commit it:\n"
                    f"  cp {target} {repo_copy}"
                )
                print(json.dumps({"decision": "allow", "reason": msg}))
                return
            else:
                # Check if repo copy is outdated (different size as quick heuristic)
                try:
                    if target.stat().st_size != repo_copy.stat().st_size:
                        msg = (
                            f"Deployed file {target.name} differs from repo copy.\n"
                            f"Sync: cp {target} {repo_copy}"
                        )
                        print(json.dumps({"decision": "allow", "reason": msg}))
                        return
                except OSError:
                    pass


if __name__ == "__main__":
    main()
```

### Step 2: Register in settings.json

Add to the existing `Write|Edit` PostToolUse matcher:

```json
{
  "type": "command",
  "command": "python3 ~/.claude/hooks/track-artifacts-in-repo.py"
}
```

### Step 3: Verify

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"/Users/cevin/.claude/hooks/new-hook.py"}}' | python3 ~/.claude/hooks/track-artifacts-in-repo.py
```

Expected: JSON reminder about missing repo copy.

### Step 4: Copy to repo

```bash
cp ~/.claude/hooks/track-artifacts-in-repo.py /Users/cevin/.claude/skills/coding-team/hooks/track-artifacts-in-repo.py
```

---

## Task 4: Create New Rules (F3b, F3c, F3d)

**Files:**
- Create: `~/.claude/rules/dark-features.md`
- Create: `~/.claude/rules/precomputation.md`
- Create: `~/.claude/rules/chunk-taxonomy-work.md`

**Model:** haiku

### Step 1: Create dark-features.md (F3b)

```markdown
---
globs:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.tsx"
  - "**/*.jsx"
---

# Dark Feature Detection

When reviewing or auditing code, check for implemented-but-unwired features:

- After implementing a feature, verify it is reachable from at least 1 entry point (route, CLI command, event handler, or test)
- Search for exported functions/classes that have 0 callers outside their own module — these may be dark features
- Check that new routes/endpoints are registered in the router, not just defined
- Verify event handlers are subscribed, not just declared
- If a feature exists in code but has no path to execution, flag it explicitly: "DARK FEATURE: {name} is implemented but not wired to any entry point"
```

### Step 2: Create precomputation.md (F3c)

```markdown
---
globs:
  - "**/.claude/skills/**/*.md"
  - "**/SKILL.md"
  - "**/.claude/agents/**/*.md"
---

# Pre-computation Rule for Orchestrators

Before dispatching worker agents, pre-compute external data they will need:

- Run dependency audits (`npm audit`, `pip audit`, `cargo audit`) at orchestrator level and pass results as data to workers
- Fetch CVE databases or security advisories before dispatching security review workers
- Run secret scanning tools before dispatching code review workers
- Gather test coverage reports before dispatching test improvement workers
- Read configuration files before dispatching workers that need config context

Workers under context pressure skip external tool calls. The orchestrator has more budget — do the I/O upfront and pass structured data to workers via their prompt.
```

### Step 3: Create chunk-taxonomy-work.md (F3d)

```markdown
---
globs:
  - "**/.claude/skills/**/*.md"
  - "**/SKILL.md"
  - "**/.claude/agents/**/*.md"
---

# Chunking Large Analysis Tasks

Large taxonomy, disambiguation, or classification tasks must be chunked to avoid context compaction mid-analysis:

- Break taxonomy work into clusters of 5-8 items per agent call — not 20+ items in one call
- Each chunk should be independently verifiable: include acceptance criteria per chunk
- Pass the full taxonomy as read-only reference but assign only 1 cluster for modification per agent
- After each chunk completes, verify results before dispatching the next chunk
- If an agent's output shows signs of context pressure (truncation, skipped items, reduced quality), reduce chunk size by 50%

Threshold: any analysis touching more than 10 items should be chunked. This applies to skill disambiguation, code audit findings, migration checklists, and similar batch work.
```

### Step 4: Verify

Confirm all 3 files exist and have valid YAML frontmatter.

---

## Task 5: Extend skill-files.md Rule (F3e)

**Files:**
- Modify: `~/.claude/rules/skill-files.md`

**Model:** haiku

### Step 1: Add identity and named rationalizations guidance

Append to the existing bullet list in `skill-files.md`:

```markdown
- Lead with identity framing in the first line: "You are the [role]" — this sets behavioral defaults stronger than any prohibition
- Name the top 3 rationalizations agents use to skip the rule, and add them as explicit compliance triggers:
  - "Only warnings, not errors" — warnings ARE errors for quality gates
  - "I'll do it myself since it's small" — size does not exempt delegation rules
  - "The tool isn't available" — verify availability before assuming; use fallback patterns
- When a prohibition is necessary, pair it with the named rationalization: "NEVER skip tests. Known rationalization: 'only warnings, no errors' — this does not apply"
```

### Step 2: Verify

Read the file and confirm it stays under 25 lines (well within the 200-line skill limit).

---

## Task 6: Create Project-Level CLAUDE.md (F4)

**Files:**
- Create: `/Users/cevin/.claude/projects/-Users-cevin--claude-skills-coding-team/CLAUDE.md`

**Model:** opus

### Step 1: Create project CLAUDE.md

This file provides project-specific context for the coding-team repo. It should cover:

1. What this repo IS (team coordination infrastructure, not a product)
2. File layout and conventions
3. Hook development patterns (JSON stdin/stdout, exit 0 always, settings.json registration)
4. Rule development patterns (YAML frontmatter globs, concise guidance)
5. Skill development patterns (under 200 lines, identity framing, verification steps)
6. Testing approach (manual testing via echo pipe for hooks, no pytest for hooks)
7. Deployment: files are tracked in repo AND deployed to ~/.claude/

Content should be concise (under 80 lines) and reference existing CLAUDE.md sections rather than duplicating them.

```markdown
# coding-team Repository

This repo contains the coding-team skill infrastructure: hooks, agents, skills, rules, and plans for Claude Code automation.

## What This Repo Is

Team coordination infrastructure — NOT a product. Files here are deployed to `~/.claude/` and define how Claude Code agents behave, coordinate, and self-correct.

## Layout

```
hooks/          → Python/Shell hooks (deployed to ~/.claude/hooks/)
agents/         → Native agent definitions (deployed to ~/.claude/agents/)
skills/         → Skill definitions with SKILL.md entry points
docs/plans/     → Implementation plans
docs/memory/    → Feedback and project memory
phases/         → Orchestration phase definitions
```

## Hook Development

- **Protocol:** Read JSON from stdin, write JSON to stdout. Always exit 0.
- **Output format:** `{"decision": "allow", "reason": "..."}` or no output (silent pass)
- **Invalid JSON or non-zero exit breaks ALL tool calls** — this is the #1 failure mode
- **Registration:** Every hook must be registered in `~/.claude/settings.json` under the correct event type and matcher
- **Testing:** `echo '{"tool_name":"X","tool_input":{...}}' | python3 hook.py`
- **Dual tracking:** Files live at `~/.claude/hooks/` (deployed) AND `hooks/` in this repo. Always update both.
- **Style:** Use pathlib over os.path. Catch specific exceptions, never bare except. Use f-strings.

## Rule Development

- YAML frontmatter with `globs:` array targeting relevant file patterns
- Keep rules concise: 5-15 bullets max
- Use identity framing and named rationalizations (see skill-files.md rule)

## Skill Development

- Keep under 200 lines — context saturation degrades compliance beyond this
- Identity framing in first line: "You are the [role]"
- Include verification steps in every phase
- Cross-reference related skills to prevent routing collisions

## Deployment

After modifying any file in this repo:
1. Copy to the deployed location (`~/.claude/hooks/`, `~/.claude/rules/`, etc.)
2. If a hook, verify settings.json registration
3. Test with echo-pipe before considering done
4. Commit to this repo so changes are tracked
```

### Step 2: Verify

Confirm the file exists and is under 80 lines.

---

## Task 7: Enhance context-budget-warning.py with Token Heuristic (F6)

**Files:**
- Modify: `~/.claude/hooks/context-budget-warning.py` + repo copy

**Model:** opus

### Step 1: Add tool-call-count heuristic

Since Claude Code doesn't expose context usage, use metrics-logger JSONL data as a proxy. Count tool calls in the current session — each tool call consumes roughly 500-2000 tokens of context. Use this to estimate context utilization.

Add a new function `estimate_from_tool_count()` that:
1. Reads today's JSONL from `~/.claude/metrics/`
2. Filters to current session ID
3. Counts tool calls
4. Maps to estimated context percentage: 50 calls ≈ 50%, 100 calls ≈ 70%, 150 calls ≈ 85%, 200+ calls ≈ 95%
5. Returns the estimated percentage

Add this as Source 4 in `get_context_percent()`, after the temp file check. Update the docstring to document the heuristic and its limitations.

Update the `KNOWN_LIMITATION` docstring to note that Source 4 is now a working heuristic (imprecise but better than nothing).

```python
# Source 4: Heuristic from tool call count (via metrics-logger JSONL)
# Imprecise but provides a working signal when no other source is available.
# Calibration: based on typical 200K context window, ~1K tokens per tool call average.
estimated = estimate_from_tool_count()
if estimated is not None:
    return estimated
```

The `estimate_from_tool_count` function:

```python
def estimate_from_tool_count() -> float | None:
    """Estimate context usage from tool call count in current session.

    Reads metrics-logger JSONL for today, counts tool calls matching
    the current session ID. Maps count to estimated percentage using
    a conservative linear model.

    Calibration assumptions (200K token window):
    - Average tool call consumes ~1000 tokens (input + output + reasoning)
    - 50 calls ≈ 25% (50K tokens)
    - 100 calls ≈ 50% (100K tokens)
    - 150 calls ≈ 75% (150K tokens)
    - 200 calls ≈ 95% (approaching limit)

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
```

Also add the required imports (`from pathlib import Path`, `from datetime import datetime, timezone`).

### Step 2: Verify

```bash
echo '{}' | python3 ~/.claude/hooks/context-budget-warning.py
```

Expected: No output (too few tool calls) or context warning if metrics exist.

### Step 3: Copy to repo

```bash
cp ~/.claude/hooks/context-budget-warning.py /Users/cevin/.claude/skills/coding-team/hooks/context-budget-warning.py
```

---

## Task 8: Create agent-quality-tracker.py PostToolUse Hook (F7)

**Files:**
- Create: `~/.claude/hooks/agent-quality-tracker.py` + repo copy
- Modify: `~/.claude/settings.json`

**Model:** sonnet

### Step 1: Create the hook script

PostToolUse hook on `Skill` that logs agent outcome signals to a JSONL file for later analysis.

```python
#!/usr/bin/env python3
"""Claude Code PostToolUse hook: track agent/skill quality signals.

Fires after Skill tool completes. Logs outcome signals to
~/.claude/metrics/agent-quality-{date}.jsonl for trend analysis.

Signals captured:
- Skill name and duration (if available)
- Whether the skill produced output or errored
- Session context (session ID, timestamp)
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

METRICS_DIR = Path.home() / ".claude" / "metrics"


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    if tool_name != "Skill":
        return

    tool_input = event.get("tool_input", {})
    tool_result = event.get("tool_result", {})

    skill_name = tool_input.get("skill_name", tool_input.get("skill", "unknown"))

    # Determine outcome
    result_str = ""
    if isinstance(tool_result, dict):
        result_str = tool_result.get("stdout", "") + tool_result.get("stderr", "")
    elif isinstance(tool_result, str):
        result_str = tool_result

    has_output = len(result_str.strip()) > 0
    has_error = False
    if isinstance(tool_result, dict):
        exit_code = tool_result.get("exit_code")
        if exit_code is not None and exit_code != 0:
            has_error = True
    if any(marker in result_str.lower() for marker in ["error", "traceback", "exception"]):
        has_error = True

    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = METRICS_DIR / f"agent-quality-{today}.jsonl"

    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill": skill_name,
        "has_output": has_output,
        "has_error": has_error,
        "output_length": len(result_str),
        "session": os.environ.get("CLAUDE_SESSION_ID", "unknown"),
    }

    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # metrics are best-effort


if __name__ == "__main__":
    main()
```

### Step 2: Register in settings.json

Add to the existing `Skill` PostToolUse matcher (alongside `coding-team-done.py`):

```json
{
  "type": "command",
  "command": "python3 ~/.claude/hooks/agent-quality-tracker.py"
}
```

### Step 3: Verify

```bash
echo '{"tool_name":"Skill","tool_input":{"skill":"coding-team"},"tool_result":"completed successfully"}' | python3 ~/.claude/hooks/agent-quality-tracker.py
```

Expected: No stdout (logs to file). Check `~/.claude/metrics/agent-quality-*.jsonl` for the record.

### Step 4: Copy to repo

```bash
cp ~/.claude/hooks/agent-quality-tracker.py /Users/cevin/.claude/skills/coding-team/hooks/agent-quality-tracker.py
```

---

## Task 9: Fix coding-team-active.py Dynamic Skill Matching (F8)

**Files:**
- Modify: `~/.claude/hooks/coding-team-active.py` + repo copy

**Model:** haiku

### Step 1: Replace hardcoded SKILL_NAMES with dynamic matching

Instead of maintaining a static set, read skill names dynamically from the skills directory at startup. Fall back to the static set if the directory read fails.

```python
#!/usr/bin/env python3
"""PreToolUse hook: mark coding-team as active when a coding-team skill is invoked."""
import json
import sys
import time
from pathlib import Path

ACTIVE_FILE = "/tmp/coding-team-active"
SKILLS_DIR = Path.home() / ".claude" / "skills" / "coding-team" / "skills"

# Fallback if directory scan fails
FALLBACK_SKILLS = {
    "coding-team", "debug", "verify", "tdd", "review-feedback", "worktree",
    "parallel-fix", "prompt-craft", "second-opinion", "scope-lock",
    "scope-unlock", "release", "retrospective", "doc-sync",
}


def get_skill_names():
    """Discover skill names from the skills directory. Falls back to static set."""
    try:
        if SKILLS_DIR.is_dir():
            names = set()
            for item in SKILLS_DIR.iterdir():
                if item.is_dir() and (item / "SKILL.md").exists():
                    names.add(item.name)
            if names:
                # Always include the top-level "coding-team" skill
                names.add("coding-team")
                return names
    except OSError:
        pass
    return FALLBACK_SKILLS


try:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool == "Skill":
        skill_name = tool_input.get("skill_name", tool_input.get("skill", ""))
        skill_names = get_skill_names()
        if skill_name in skill_names:
            with open(ACTIVE_FILE, "w") as f:
                f.write(str(time.time()))
except (json.JSONDecodeError, ValueError, KeyError):
    pass

print(json.dumps({"decision": "allow"}))
```

### Step 2: Verify

```bash
echo '{"tool_name":"Skill","tool_input":{"skill":"coding-team"}}' | python3 ~/.claude/hooks/coding-team-active.py
cat /tmp/coding-team-active
```

Expected: JSON allow decision. File `/tmp/coding-team-active` contains a timestamp.

### Step 3: Copy to repo

```bash
cp ~/.claude/hooks/coding-team-active.py /Users/cevin/.claude/skills/coding-team/hooks/coding-team-active.py
```

---

## Task 10: Create identity-framing-check.py PreToolUse Hook (F9)

**Files:**
- Create: `~/.claude/hooks/identity-framing-check.py` + repo copy
- Modify: `~/.claude/settings.json`

**Model:** sonnet

### Step 1: Create the hook script

PreToolUse hook on `Write` that checks if the file being written is an agent or skill instruction file and validates it starts with identity framing.

```python
#!/usr/bin/env python3
"""Claude Code PreToolUse hook: validate identity framing in agent/skill files.

Fires on Write. If the target file is an agent definition (.md in agents/)
or skill instruction (SKILL.md, phases/*.md), checks that the content
begins with identity framing ("You are...").

Advisory only — allows the write but surfaces a warning if identity framing
is missing.
"""
import json
import re
import sys

# Patterns for files that should have identity framing
IDENTITY_FILE_PATTERNS = [
    r"\.claude/agents/.*\.md$",
    r"\.claude/skills/.*/SKILL\.md$",
    r"\.claude/skills/.*/phases/.*\.md$",
    r"agents/.*\.md$",
    r"skills/.*/SKILL\.md$",
]

# Identity framing indicators (case-insensitive)
IDENTITY_MARKERS = [
    r"^you are ",
    r"^your role",
    r"^as the ",
    r"^you serve as",
]


def is_instruction_file(file_path):
    """Check if the file path matches known instruction file patterns."""
    for pattern in IDENTITY_FILE_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def has_identity_framing(content):
    """Check if content starts with identity framing (after frontmatter/headers)."""
    if not content:
        return False

    lines = content.split("\n")
    in_frontmatter = False
    content_started = False

    for line in lines:
        stripped = line.strip()

        # Skip YAML frontmatter
        if stripped == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue

        # Skip empty lines and markdown headers
        if not stripped:
            continue
        if stripped.startswith("#"):
            content_started = True
            continue

        # First non-header, non-empty line after headers
        if content_started or not stripped.startswith("#"):
            for marker in IDENTITY_MARKERS:
                if re.match(marker, stripped, re.IGNORECASE):
                    return True
            # Check first 3 content lines
            return False

    return False


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = event.get("tool_name", "")
    if tool_name != "Write":
        return

    tool_input = event.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    content = tool_input.get("content", "")

    if not file_path or not is_instruction_file(file_path):
        return

    if not has_identity_framing(content):
        msg = (
            f"Identity framing missing in {file_path}.\n"
            f"Agent/skill instruction files should start with identity framing: "
            f"'You are the [role]' — this sets behavioral defaults stronger than prohibitions.\n"
            f"See skill-files.md rule for guidance."
        )
        print(json.dumps({"decision": "allow", "reason": msg}))


if __name__ == "__main__":
    main()
```

### Step 2: Register in settings.json

Add a new PreToolUse matcher for `Write` (or add to an existing matcher):

```json
{
  "matcher": "Write",
  "hooks": [
    {
      "type": "command",
      "command": "python3 ~/.claude/hooks/identity-framing-check.py"
    }
  ]
}
```

Note: There is no existing `Write`-only PreToolUse matcher. The existing `Edit|Write` matcher runs `no-mocks.py`. We need a separate `Write` matcher since this hook only applies to Write (Edit doesn't have `content` in tool_input).

### Step 3: Verify

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"/Users/cevin/.claude/agents/test.md","content":"# Test Agent\n\nDo things."}}' | python3 ~/.claude/hooks/identity-framing-check.py
```

Expected: JSON warning about missing identity framing.

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"/Users/cevin/.claude/agents/test.md","content":"# Test Agent\n\nYou are the test agent."}}' | python3 ~/.claude/hooks/identity-framing-check.py
```

Expected: No output (identity framing present).

### Step 4: Copy to repo

```bash
cp ~/.claude/hooks/identity-framing-check.py /Users/cevin/.claude/skills/coding-team/hooks/identity-framing-check.py
```

---

## Task 11: Register All New Hooks in settings.json (F2, F3a, F7, F9)

**Files:**
- Modify: `~/.claude/settings.json`

**Model:** sonnet (must coordinate all 4 registrations in one edit to keep JSON valid)

### Step 1: Add all new hook registrations

The following changes to `~/.claude/settings.json`:

**SessionStart** — add metrics-analyzer.py to existing array:
```json
{
  "type": "command",
  "command": "python3 ~/.claude/hooks/metrics-analyzer.py"
}
```

**PostToolUse `Write|Edit`** — add track-artifacts-in-repo.py to existing array:
```json
{
  "type": "command",
  "command": "python3 ~/.claude/hooks/track-artifacts-in-repo.py"
}
```

**PostToolUse `Skill`** — add agent-quality-tracker.py to existing array:
```json
{
  "type": "command",
  "command": "python3 ~/.claude/hooks/agent-quality-tracker.py"
}
```

**PreToolUse** — add new `Write` matcher:
```json
{
  "matcher": "Write",
  "hooks": [
    {
      "type": "command",
      "command": "python3 ~/.claude/hooks/identity-framing-check.py"
    }
  ]
}
```

### Step 2: Verify

```bash
python3 -c "import json; json.load(open(os.path.expanduser('~/.claude/settings.json')))" && echo "Valid JSON"
```

---

## Failure Modes

| Risk | Impact | Mitigation |
|------|--------|------------|
| Hook outputs invalid JSON | Breaks ALL tool calls for session | Every hook must be tested with echo-pipe before deploying |
| Hook exits non-zero | Same as above | Wrap main() in try/except, always exit 0 |
| settings.json becomes invalid JSON | Breaks ALL hooks | Validate JSON after every edit. Make one atomic edit for all registrations |
| metrics-analyzer reads huge JSONL | Slow SessionStart | Cap at MAX_FILES_TO_CHECK=3 and limit record processing |
| identity-framing-check false positives | Annoys users on non-instruction files | Narrow file pattern matching to known instruction paths only |
| context-budget-warning heuristic is wrong | Premature or late warnings | Conservative calibration, document as heuristic with known imprecision |

---

## NOT in Scope

- Modifying any skill SKILL.md files (those are instruction files, not hooks)
- Creating new agents
- Changing the hook protocol itself
- Modifying ci-orphan-detector.sh or patch-github-plugin.sh
- Adding new MCP tools or permissions
- Changing any deployed service configuration

---

## Execution Order

Tasks can be executed in parallel EXCEPT:
- Task 11 (settings.json registration) must run AFTER Tasks 2, 3, 8, 10 create their hook files
- Task 7 (context-budget-warning) needs import additions — can run independently

Recommended parallel groups:
1. **Group A (parallel):** Tasks 1, 2, 3, 4, 5, 8, 9, 10
2. **Group B (sequential after A):** Task 11 (settings.json — all registrations at once)
3. **Group C (parallel with A):** Task 6 (project CLAUDE.md), Task 7 (context-budget-warning)

---

## Traceability Table

| Finding | Status | Task | Notes |
|---------|--------|------|-------|
| F1: loop-detection behavioral correction | Fix | Task 1 | Pattern classification + category-specific recovery strategies |
| F2: metrics-analyzer SessionStart hook | Fix | Task 2 | Reads metrics-logger JSONL, surfaces anomalies |
| F3a: track-artifacts-in-repo hook | Fix | Task 3 | PostToolUse Write\|Edit, checks repo copy exists |
| F3b: dark-features rule | Fix | Task 4 | Reachability check guidance for code review |
| F3c: precomputation rule | Fix | Task 4 | Pre-compute external data before dispatching workers |
| F3d: chunk-taxonomy-work rule | Fix | Task 4 | Chunk large analysis to avoid context compaction |
| F3e: identity + rationalizations in skill-files.md | Fix | Task 5 | Extend existing rule with 3 new bullets |
| F4: project-level CLAUDE.md | Fix | Task 6 | coding-team repo context for new sessions |
| F6: context-budget-warning token heuristic | Fix | Task 7 | Tool-call-count proxy from metrics JSONL |
| F7: agent-quality-tracker PostToolUse hook | Fix | Task 8 | Logs skill outcome signals to JSONL |
| F8: coding-team-active dynamic matching | Fix | Task 9 | Discover skills from directory, fallback to static set |
| F9: identity-framing-check PreToolUse hook | Fix | Task 10 | Validates identity preamble in agent/skill files |
