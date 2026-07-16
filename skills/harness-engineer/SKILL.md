---
name: harness-engineer
description: "Use when designing or auditing Claude Code harness infrastructure — hooks, rules, settings, constraint gaps, maturity assessment. Do NOT use for instruction text quality (use /prompt-craft instead). Do NOT use for code implementation (use /coding-team instead)."
---

# /harness-engineer — Harness Infrastructure Design & Audit

Designs and audits the infrastructure that governs AI agent behavior: hooks, rules, settings, observability, constraint promotion, and maturity progression. Born from the CIVC six-verb × surface grid (afford, inform, constrain, verify, correct, evolve) and trained on the Harness Engineering knowledge base.

## When to Use

| Situation | Use this | Not this |
|-----------|----------|----------|
| "Audit my harness setup" | /harness-engineer | — |
| "Design a hook for X" | /harness-engineer | — |
| "Should this be a hook or a rule?" | /harness-engineer | — |
| "What maturity level am I at?" | /harness-engineer | — |
| "This feedback should become a constraint" | /harness-engineer | — |
| "This SKILL.md has vague language" | — | /prompt-craft |
| "CC keeps misinterpreting instructions" | — | /prompt-craft diagnose |
| "Implement these hook changes" | — | /coding-team |

## Modes

### 1. Audit (default when no args)

Full harness audit against the CIVC six-verb × surface grid and maturity model.

**Division of labor:** harness-map collects and flags; harness-engineer judges and designs; coding-team implements.

**What it does:**
- Consumes the harness-map inventory (hooks, rules, settings, instruction files) rather than re-inventorying by hand
- Classifies each by verb × surface (the CIVC six-verb × six-surface grid)
- Checks feedback memories for promotion gaps (prompt fix → hook)
- Assesses maturity level (0-4) and identifies the bridge to next level
- Produces a prioritized findings report

**Invoke:** `/harness-engineer` or `/harness-engineer audit`

### 2. Design

Design a new hook, rule, or constraint for a specific failure mode.

**What it does:**
- Classifies the constraint by verb × surface
- Searches the KB for prior art and patterns
- Specifies hook type, matcher, logic, registration, escape hatch
- Assesses side effects and conflicts with existing hooks

**Read when designing a hook:** `~/.claude/rules-on-demand/hook-stdlib-naming.md` — the hook naming/stdlib conventions. Load this rule only in Design mode; it does not apply to audit, assess, or verify.

**Invoke:** `/harness-engineer design <description of what to constrain>`

### 3. Assess

Maturity assessment — places the harness on both maturity ladders with a quantitative, per-dimension score (lighter than a full audit, but not a one-number label).

**What it does:**
- Reads current harness state
- Maps against BOTH the infra Level 0-4 ladder (Ch 22) and the vibe-coding spec-maturity ladder
- Scores each dimension with the quantitative rubric — the per-dimension scores are the deliverable, not a single level label
- Judges steering density model-conditionally; scopes findings core vs overlay
- Applies the Evolve test before any Level-4 claim

**Invoke:** `/harness-engineer assess`

### 4. Verify

Adjudicate prior harness-edit predictions against accumulated evidence.

**What it does:**
- Runs `python3 ~/.claude/bin/harness decisions --pending` to list predictions awaiting a verdict
- For each prediction, gathers evidence: `harness metrics` trends, `python3 ~/.claude/bin/harness verify --attribution` (plus `--phi`/`--overview` as relevant) to ground the verdict in failure-attribution and loop-risk data rather than metrics trends alone, the git/file diff of the edited component, and direct observation of behavior since the edit
- Adjudicates each against its `predicted_impact`, then records the verdict: run `mktemp /tmp/verify-note-XXXXXX.txt`, write the note to that literal path with the Write tool, then run `python3 ~/.claude/bin/harness decisions --verify <id> --status verified|refuted --note "$(cat <literal-path>)"` with the literal path substituted
- If evidence is insufficient, leaves the prediction pending with a noted reason — never guesses a verdict

**Documented limitation:** hard auto-verification against per-component failure data is a later collector step. Until then, verdicts use trends + diffs + direct observation, not automated failure-rate comparison.

**Invoke:** `/harness-engineer verify`

## Decision Observability

You are running a predict→verify loop, not guess-and-tweak. Every harness edit `/harness-engineer` proposes MUST emit a prediction row BEFORE the edit ships, capturing `{failure_evidence, root_cause, targeted_fix, predicted_impact, verify_by_session}` (plus `id`, `date`, `component`). Never inline free-text field values inside shell quotes — run `mktemp /tmp/decision-XXXXXX.json`, write the JSON to that literal path with the Write tool, then run `python3 ~/.claude/bin/harness decisions --log "$(cat <literal-path>)"` with the literal path substituted.

The prediction is the contract: it states what failure the edit fixes and how you will know it worked. A later `/harness-engineer verify` run adjudicates it. An edit with no prediction is unverifiable — exactly the guess-and-tweak this loop removes.

Named rationalization: "this change is small/obvious — no prediction needed." No harness edit ships without a prediction. A batch of mechanical edits — each ≤1 file, ≤20 lines, no behavior/logic change, max 5 edits per row — MAY share ONE prediction row enumerating every edit's file:line, but the ABSENCE of a prediction is never permitted and the shared row never changes the task's review tier below Medium. Small edits are the ones most often shipped on a hunch and never checked — that risk is why the invariant holds even under the batch escape.

Never paste raw secrets, tokens, or credentials into any prediction field or `--note` — the decisions log is git-tracked and remotely backed up; reference the secret's location instead (e.g. "the token in settings.json env").

## Routing

This skill dispatches the `ct-harness-engineer` native agent (`~/.claude/agents/ct-harness-engineer.md`).

**For standalone use:** Dispatch via Agent tool with model `opus`. Pass the mode (audit/design/assess/verify) and any user arguments.

**From /coding-team Phase 2:** The team leader dispatches as a design worker alongside other specialists. The harness engineer evaluates the task through the constraint/observability lens.

**From /coding-team Phase 5 audit loop:** Dispatched as an additional auditor when modified files match: `settings.json`, `hooks/*`, `rules/*`, `*.claude/CLAUDE.md`, `agents/*.md`. Dispatch is conditional (like prompt-craft-auditor). Checks constraint completeness, hook correctness, and promotion opportunities.

## Dispatch Template

When invoking the agent, include:

```
Mode: [audit | design | assess | verify]
Working directory: [path]
User request: [what the user asked for]

[For design mode:]
Failure mode: [what should be prevented]
Current mitigation: [prompt text, rule, or nothing]
Trigger: [when should the constraint fire]
```

The agent has access to the engram CLI (`engram search … --json`, `engram query-nodes … --json`) for KB lookups, codesight-mcp for code analysis, and Bash for inspecting hook scripts and settings.

**Fallback if `engram` is unavailable:** if `engram` is not on PATH, or the dev server is down, retry once; if it still fails, degrade to Grep/Read over `~/.claude/skills/coding-team/agents/reference/harness-engineer-reference.md` (key chapters, guaranteed present) and — best-effort, only if present — the vault KB at `~/Documents/obsidian-vault/AI/kb/Harness-Engineering/`, for the same lookups. Consistent with the repo's MCP-resilience pattern: retry once max, then degrade to built-in tools.
