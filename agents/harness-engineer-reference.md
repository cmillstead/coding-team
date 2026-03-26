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
