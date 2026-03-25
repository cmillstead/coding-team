---
name: review-feedback
description: "Use when you RECEIVED review comments and need to evaluate and address them — from PR reviewers, teammates, users, or external contributors. Not for reviewing code yourself (use /review for that). Technical evaluation protocol: read, understand, verify against codebase, evaluate technically, then respond or push back with reasoning. No performative agreement."
---

# /review-feedback — Handling Code Review

When invoked standalone:
- If the user pastes review comments, start at step 1 (READ)
- If the user says "I got feedback on my PR" without specifics, ask them to paste or link the feedback
- Apply verification protocol before claiming any fix is complete

When invoked from /coding-team, the lead provides review context. Skip the above.

---

## The Response Pattern

1. **READ** — complete feedback without reacting
2. **UNDERSTAND** — restate the requirement in your own words (or ask)
3. **VERIFY** — check against codebase reality
4. **EVALUATE** — technically sound for THIS codebase?
5. **RESPOND** — technical acknowledgment or reasoned pushback
6. **IMPLEMENT** — one item at a time, test each

## Forbidden Responses

Never say: "You're absolutely right!", "Great point!", "Thanks for catching that!"

Instead: restate the technical requirement, ask clarifying questions, push back with reasoning if wrong, or just fix it silently. Actions > words.

## Handling Unclear Feedback

If ANY item is unclear, STOP. Do not implement anything yet. Ask for clarification on all unclear items first.

Items may be related — partial understanding leads to wrong implementation.

## When to Push Back

Push back when:
- Suggestion breaks existing functionality
- Reviewer lacks full context
- Violates YAGNI (unused feature)
- Technically incorrect for this stack
- Conflicts with prior architectural decisions

How: use technical reasoning, reference working tests/code, ask specific questions.

## From External Reviewers

Before implementing external suggestions:
1. Technically correct for THIS codebase?
2. Breaks existing functionality?
3. Reason for current implementation?
4. Works on all platforms/versions?
5. Does reviewer understand full context?

## Implementation Order

For multi-item feedback:
1. Clarify anything unclear FIRST
2. Blocking issues (breaks, security)
3. Simple fixes (typos, imports)
4. Complex fixes (refactoring, logic)
5. Test each fix individually
6. Verify no regressions

## Acknowledging Correct Feedback

```
"Fixed. [Brief description of what changed]"
"Good catch — [specific issue]. Fixed in [location]."
[Or just fix it and show in the code]
```

## If Your Pushback Was Wrong

```
"You were right — I checked [X] and it does [Y]. Implementing now."
```

State the correction factually and move on. No long apology.

## Verification Gate

Before claiming any fix is complete:
1. IDENTIFY: What command proves this?
2. RUN: Execute it fresh
3. READ: Full output, check exit code
4. VERIFY: Does output confirm the claim?
5. ONLY THEN: Make the claim
