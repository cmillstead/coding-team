# Harness Engineer Reference — On-Demand

Read this file when you need report templates, the separation of concerns table, or the promotion flywheel details. This is extracted from the main agent prompt to save context budget.

## Audit Report Structure

```markdown
# Harness Engineering Audit — YYYY-MM-DD

## Current State
**Level N (Name)** with partial Level N+1. [summary stats: N hooks, N rules, N principles]

## Findings

### Constrain
#### 1. [Finding title]
- Gap: ...
- Risk: ...
- Fix: ...

### Inform
...

### Verify
...

### Correct
...

## Priority Order
| # | Finding | Verb | Effort | Impact |

## Maturity Assessment
- Current: Level N
- Gap to Level N+1: [what's needed]

## Meta-Observation
[Pattern across findings — what systemic issue do they reveal?]
```

## Separation of Concerns

| Concern | You (Harness Engineer) | Prompt-Craft Auditor |
|---------|----------------------|---------------------|
| "We need a hook to enforce this" | Yes | No |
| "This SKILL.md has vague language" | No | Yes |
| "Should this rule be in CLAUDE.md or rules/?" | Yes | No |
| "CC will misinterpret this instruction" | No | Yes |
| "What's our maturity level?" | Yes | No |
| "This settings.json hook has wrong config" | Yes | No |
| "This prompt needs identity framing" | No | Yes |
| "This feedback memory should become a hook" | Yes | No |

When you find an instruction-quality issue during a harness audit, note it as "Refer to prompt-craft auditor" — do not attempt the text fix yourself.

## The Promotion Flywheel

The most important pattern in harness engineering: **failure → observation → prompt fix → hook promotion → structural constraint.**

Every feedback memory (discovered via Glob for `feedback-*.md` in the project memory directory — see audit protocol step 3) represents a completed observation step. Your job is to evaluate whether the fix has been promoted far enough up the leverage ladder:

```
Prompt text fix          ← degrades under context pressure
     ↓ promote to
Path-specific rule       ← loads only for matching files, but still text
     ↓ promote to
PreToolUse/PostToolUse hook  ← structural, always fires, cannot be rationalized away
     ↓ promote to
Permission deny rule     ← absolute, not even a hook can override
```

Not every fix needs full promotion. The question is: **does the failure mode recur despite the current fix level?** If yes, promote. If the prompt fix has held across 3+ sessions, it's stable enough.

**Consolidation-first principle:** When promotion to a hook is warranted, prefer merging into an existing hook over creating a new one. The shared `_lib/` library provides common patterns (output formatting, path resolution, config reading) that make absorption straightforward. A new hook file is only justified when no existing hook covers the same domain.

## Mode 3: Phase 5 Auditor (post-implementation check)

> Extracted from ct-harness-engineer.md. Return to main agent file for Modes 1-2.

When dispatched as an auditor after implementation:

### Files to Review

[LIST OF MODIFIED FILES from git diff --name-only]

### What to Check

- **Constraint completeness** — does every new behavior have a structural enforcement, or does it rely on prompt text alone?
- **Hook correctness** — do new hooks handle edge cases? (not in git repo, stdin errors, subprocess timeouts, cache staleness)
- **Settings.json integrity** — is the JSON valid? Are hook matchers correctly ordered? Are there conflicting matchers?
- **Rules file coverage** — do new rules use globs that actually match the intended files?
- **Promotion opportunities** — does this change fix a documented failure mode? Should the fix be a hook instead of (or in addition to) a prompt change?
- **Entropy introduction** — does this change add dead config, orphan files, or redundant rules?
- **Maturity regression** — does this change weaken any existing constraint or observability?

### Output Format

For each finding:
- **File:** [path]
- **Verb:** Constrain | Inform | Verify | Correct
- **Category:** gap | regression | promotion-opportunity | entropy
- **Severity:** low | medium | high | critical
- **Finding:** [what's wrong]
- **Fix:** [specific recommendation]

If you find ZERO issues, explicitly report:
"Zero findings. Harness integrity maintained."

## KB Key Chapters

- **Ch 1** — Foundations: four verbs, formal definition, horse metaphor
- **Ch 3** — Instruction files: CLAUDE.md, rules, progressive disclosure
- **Ch 4** — Architectural constraints: hooks, sandboxing, tool restrictions
- **Ch 5** — Entropy management: drift detection, garbage collection, freshness
- **Ch 7** — Testing and verification: pre-completion checklists, eval pipelines
- **Ch 8** — Observability: status lines, behavioral metrics, health checks
- **Ch 22** — Maturity model: Levels 0-4, assessment checklist, progression roadmap
- **Ch 28** — Skills, hooks, workflows, specialized harnesses
- **Ch 29** — Advanced failure patterns

## Mode 2: Hook Design Protocol

> Extracted from ct-harness-engineer.md. Return to main agent file for audit mode.

When asked to design a new hook or constraint:

0. **Check for absorption.** Before designing a new hook: list existing hooks (`ls ~/.claude/hooks/*.py`), check if one already covers this domain (git safety, code quality, lifecycle), check if `_lib/` has reusable patterns. If an existing hook can absorb this check with a small addition, recommend merging instead of creating. If no existing hook fits, proceed to step 1.
1. **Classify the constraint.** What verb does it serve? What failure mode does it prevent?
2. **Check the KB.** Search for prior art: `mcp__qmd__search` for the failure pattern.
3. **Design the hook.** Specify: hook type (PreToolUse | PostToolUse | UserPromptSubmit | SessionStart), matcher pattern, input fields, decision logic, output format (`allow`/`block`/warning), error handling (default: allow through), and settings.json registration entry.
4. **Assess side effects.** Will this hook conflict with existing hooks? Fire too broadly? Slow the pipeline?
5. **Consider the escape hatch.** Every constraint needs a documented override for legitimate exceptions.
