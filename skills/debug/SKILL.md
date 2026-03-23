---
name: debug
description: "Use when investigating a bug, test failure, or unexpected behavior. Four-phase root cause investigation: investigate, analyze, hypothesize, implement. Dispatches parallel hypothesis teams for complex bugs. Use instead of guessing at fixes."
---

# /debug — Root Cause Investigation

When invoked standalone (not from /coding-team), read project context first:
- CLAUDE.md, recent commits (`git log --oneline -10`), failing test output
- If the user provided an error message, start at Phase 1 with that as input
- If the user said "debug" without specifics, ask what's broken

When invoked from /coding-team Phase 5, the lead provides full context. Skip the above.

---

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## Phase 1: Root Cause Investigation

1. **Read error messages carefully** — don't skip past errors. Read stack traces completely. Note line numbers, file paths, error codes.

2. **Reproduce consistently** — can you trigger it reliably? What are the exact steps? If not reproducible, gather more data — don't guess.

3. **Check recent changes** — what changed that could cause this? Git diff, recent commits, new dependencies, config changes. A regression means the root cause is in the diff.

4. **Gather evidence in multi-component systems** — before proposing fixes, add diagnostic instrumentation at each component boundary. Run once to see WHERE it breaks, THEN analyze.

5. **Trace data flow** — where does the bad value originate? What called this with the bad value? Keep tracing up until you find the source. Fix at source, not at symptom.

**Recent change analysis:** Use `mcp__plugin_github_github__list_commits` to see recent commits. For regressions, narrow the window with `git log --oneline --since="3 days ago"`. Use `mcp__plugin_github_github__get_commit` to inspect suspicious commits in detail. Recent changes are the most likely cause of new bugs.

**Trace downstream:** Use `mcp__codesight-mcp__get_callees` on failing functions to understand what they call — the bug may be in a downstream dependency, not the function itself.

**Prior bug search:** Use QMD `vector_search` tool with collection `"conversations"` and a description of the bug symptoms to find similar past bugs. Past episodes often contain root causes and fix patterns that apply to the current investigation.

**Find entry points:** Use `mcp__codesight-mcp__get_key_symbols` to identify the most significant symbols in the affected module — helps orient investigation in unfamiliar code.

**Full-text code search:** Use `mcp__codesight-mcp__search_text` for fast full-text search across indexed code — faster than grep for searching error strings, magic values, or configuration keys across large repos.

If codesight-mcp tools are not available, fall back to Grep/Read for call-site and symbol searches. Do NOT skip tracing — use whichever tools are available.

**After forming a hypothesis, lock scope:** Identify the narrowest directory containing the affected files. Restrict edits to that directory for the rest of the debug session. This prevents accidentally "fixing" unrelated code while investigating.

## Phase 2: Pattern Analysis

Check if this bug matches a known pattern:

| Pattern | Signature | Where to look |
|---|---|---|
| Race condition | Intermittent, timing-dependent | Concurrent access to shared state |
| Nil/null propagation | TypeError, AttributeError | Missing guards on optional values |
| State corruption | Inconsistent data, partial updates | Transactions, callbacks, hooks |
| Integration failure | Timeout, unexpected response | External API calls, service boundaries |
| Configuration drift | Works locally, fails in CI/staging | Env vars, feature flags, DB state |
| Stale cache | Shows old data, fixes on cache clear | Redis, CDN, in-memory caches |

**Error research:** Use the `WebSearch` tool to search for exact error messages, stack traces, or unfamiliar error codes. Library documentation, GitHub issues, and Stack Overflow often have the root cause. Search BEFORE forming hypotheses — external knowledge prevents wasted investigation.

Also check:
- **Git log** for prior fixes in the same area — recurring bugs in the same files are an architectural smell, not coincidence
- Find working examples of similar code in the codebase and compare

## Phase 3: Hypothesis and Testing

**Frontend/UI bugs:** When investigating bugs that affect the user interface (HTML, JSX, TSX, CSS, SCSS, templates, React components), use the Browse tool to screenshot the current state of the affected page BEFORE making changes. Include screenshots as evidence in your hypothesis. After applying a fix, screenshot again to show the before/after difference.

**Simple bugs (single plausible cause):** Sequential approach.
1. **Form single hypothesis** — "I think X is the root cause because Y." Be specific.
2. **Test minimally** — smallest possible change, one variable at a time.
3. **Verify** — did it work? Yes -> Phase 4. No -> form NEW hypothesis. Don't stack fixes.
4. **When you don't know** — say so. Don't pretend. Ask for help or research more.

**Complex bugs (multiple plausible causes):** Parallel hypothesis investigation.

**Check AGENT_TEAMS_AVAILABLE before dispatching any parallel investigation.**

**If AGENT_TEAMS_AVAILABLE = true and 3+ competing hypotheses (default):**

Use agent teams for parallel investigation.

1. Create team:
   `Teammate({ operation: "spawnTeam", team_name: "debug-<feature>-<timestamp>" })`

2. Create tasks (one per hypothesis):
   ```
   TaskCreate({
     subject: "Hypothesis N: <description>",
     description: "Investigate whether <hypothesis>. Gather evidence for AND against. Message other teammates if you find evidence that affects their hypothesis. Report: confirmed, refuted, or inconclusive with evidence.",
     activeForm: "Investigating..."
   })
   ```

3. Spawn investigators (one per hypothesis, all read-only Explore):
   - Spawn prompt includes: the hypothesis, relevant code paths, error context, and instruction to message peers when finding cross-cutting evidence
   - Explicit instruction: "If you find evidence that refutes another teammate's hypothesis, message them immediately via SendMessage. If another teammate sends you evidence against your hypothesis, pivot your investigation."
   - All teammates run in Explore (read-only) mode

4. Monitor via lead:
   - Watch for idle notifications (teammate finished investigating)
   - Check inbox for cross-team findings
   - When all teammates report or idle: collect results

5. Synthesize:
   - The hypothesis with the strongest confirming evidence (and no refuting evidence from peers) informs Phase 4
   - If debate produced convergence on a root cause not in any original hypothesis, use that

6. Shutdown and cleanup:
   `Teammate({ operation: "requestShutdown", target_agent_id: "<each>" })`
   Wait for approvals.
   `Teammate({ operation: "cleanup" })`

**If AGENT_TEAMS_AVAILABLE = false, or 2 hypotheses only:**

Fall back to Agent tool when agent teams are unavailable, only 2 hypotheses exist (overhead not justified), or hypotheses are trivially independent (different subsystems with no shared state).

**Fallback path:**

Dispatch a **debug team** — one agent per hypothesis, all investigating in parallel (read-only Explore agents). Each agent:
- States the hypothesis clearly
- Gathers evidence for/against
- Reports: confirmed, refuted, or inconclusive with evidence

The agent that confirms its hypothesis (or the strongest evidence) informs Phase 4.

**3-strike rule:** If 3 hypotheses fail, STOP and escalate to user with options:
- Continue with a new hypothesis (user provides direction)
- Escalate for human review (needs system knowledge)
- Add logging and wait (instrument the area, catch it next occurrence)

## Phase 4: Implementation

1. **Create failing test case** — simplest possible reproduction, automated if possible.
2. **Implement single fix** — address the root cause, ONE change at a time. No "while I'm here" improvements.
3. **Blast radius check** — if the fix touches >5 files, flag it to the user before proceeding. A large blast radius for a bug fix is a smell.
4. **Verify fix** — apply verification gate:
   1. IDENTIFY: What command proves this?
   2. RUN: Execute it fresh
   3. READ: Full output, check exit code
   4. VERIFY: Does output confirm the claim?
   5. ONLY THEN: Make the claim
5. **If fix doesn't work** — count attempts. If < 3, return to Phase 1 with new information. If >= 3, STOP.

## Phase 5: Report

Every debug session produces a structured report:

```
DEBUG REPORT
Symptom:         [what was observed]
Root cause:      [what was actually wrong]
Fix:             [what was changed, with file:line references]
Evidence:        [test output showing fix works]
Regression test: [file:line of the new test]
Blast radius:    [N files touched]
Related:         [prior bugs in same area, architectural notes]
Status:          DONE | DONE_WITH_CONCERNS | BLOCKED
```

**Save debug report to disk:**
- Determine `$REPO_ROOT` via `git rev-parse --show-toplevel`.
- Create directory `$REPO_ROOT/docs/debug/` if it does not exist using Bash tool: `mkdir -p "$REPO_ROOT/docs/debug/"`.
- Write the debug report to `$REPO_ROOT/docs/debug/YYYY-MM-DD-<symptom-slug>.md` using the Write tool. Use today's date and a kebab-case slug derived from the symptom (e.g., `2026-03-22-null-ref-in-auth-handler.md`).
- **Architectural note trigger:** If the fix touches more than 5 files (blast radius > 5) OR the "Related" field mentions prior bugs in the same area, append an `## Architectural Note` section to the saved report. The note must describe the structural pattern that makes this area bug-prone and what architectural change would prevent recurrence.
- **Eval feed-forward:** If the architectural note identifies a check that auditors should verify in future sessions, append it to `$REPO_ROOT/docs/project-evals.md` as a checklist item.
  - If `$REPO_ROOT/docs/project-evals.md` does not exist, create it using the Write tool with this exact template:

    ```markdown
    # Project-Specific Eval Criteria

    > Accumulated from retrospectives and debug sessions. The planning worker loads these as seed criteria for auditors.
    > Each item is a check that agents missed in a prior session.

    - [ ] [criterion]
    ```

  - Before appending, read the existing file and check for duplicates. Do NOT add a criterion that is already present.

## After 3+ Failed Fixes: Question Architecture

Pattern indicating an architectural problem:
- Each fix reveals new shared state/coupling in different places
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and escalate to user.** This is not a failed hypothesis — this is a wrong architecture.

## Red Flags — STOP and Follow Process

- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "It's probably X, let me fix that"
- Proposing solutions before tracing data flow
- "One more fix attempt" when already tried 2+

All of these mean: STOP. Return to Phase 1.
