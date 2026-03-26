---
name: harness-engineer
description: "Use when designing or auditing Claude Code harness infrastructure — hooks, rules, settings, constraint gaps, maturity assessment. Do NOT use for instruction text quality (use /prompt-craft instead). Do NOT use for code implementation (use /coding-team instead)."
---

# /harness-engineer — Harness Infrastructure Design & Audit

Designs and audits the infrastructure that governs AI agent behavior: hooks, rules, settings, observability, constraint promotion, and maturity progression. Born from the four verbs (constrain, inform, verify, correct) and trained on the Harness Engineering knowledge base (34 chapters).

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

Full harness audit against the four verbs and maturity model.

**What it does:**
- Inventories all hooks, rules, settings, instruction files
- Classifies each by verb (constrain/inform/verify/correct)
- Checks feedback memories for promotion gaps (prompt fix → hook)
- Assesses maturity level (0-4) and identifies the bridge to next level
- Produces a prioritized findings report

**Invoke:** `/harness-engineer` or `/harness-engineer audit`

### 2. Design

Design a new hook, rule, or constraint for a specific failure mode.

**What it does:**
- Classifies the constraint by verb
- Searches the KB for prior art and patterns
- Specifies hook type, matcher, logic, registration, escape hatch
- Assesses side effects and conflicts with existing hooks

**Invoke:** `/harness-engineer design <description of what to constrain>`

### 3. Assess

Quick maturity assessment without a full audit.

**What it does:**
- Reads current harness state
- Maps against Level 0-4 indicators from Ch 22
- Reports current level with evidence
- Lists 3 highest-leverage gaps for next level

**Invoke:** `/harness-engineer assess`

## Routing

This skill dispatches the `ct-harness-engineer` native agent (`~/.claude/agents/ct-harness-engineer.md`).

**For standalone use:** Dispatch via Agent tool with model `opus`. Pass the mode (audit/design/assess) and any user arguments.

**From /coding-team Phase 2:** The team leader dispatches as a design worker alongside other specialists. The harness engineer evaluates the task through the constraint/observability lens.

**From /coding-team Phase 5 audit loop:** Dispatched as an additional auditor when modified files match: `settings.json`, `hooks/*`, `rules/*`, `*.claude/CLAUDE.md`, `agents/*.md`. Dispatch is conditional (like prompt-craft-auditor). Checks constraint completeness, hook correctness, and promotion opportunities.

## Dispatch Template

When invoking the agent, include:

```
Mode: [audit | design | assess]
Working directory: [path]
User request: [what the user asked for]

[For design mode:]
Failure mode: [what should be prevented]
Current mitigation: [prompt text, rule, or nothing]
Trigger: [when should the constraint fire]
```

The agent has access to QMD for KB lookups, codesight-mcp for code analysis, and Bash for inspecting hook scripts and settings.
