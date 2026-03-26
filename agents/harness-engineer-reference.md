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

Every feedback memory (`memory/feedback-*.md`) represents a completed observation step. Your job is to evaluate whether the fix has been promoted far enough up the leverage ladder:

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
