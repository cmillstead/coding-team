---
name: Strategy change validated — identity + rationalizations working
description: User confirms no friction or bad behavior since identity-over-prohibition pivot and named rationalizations; only CI infra issue remained (separately fixed)
type: feedback
---

After the major harness audit (2026-03-22) and subsequent prompt-craft improvements, user reports zero friction or behavioral issues — the first clean period since the project began.

**What changed (the "strategy change"):**
1. Identity framing replaced prohibition framing for role boundaries ("you are the orchestrator" instead of "NEVER write code")
2. Named rationalizations intercept bypass reasoning ("too simple" / "already handled" / "pre-existing" named as compliance triggers)
3. Anti-recursion clauses added to all agent prompts (prevents CLAUDE.md inheritance from causing recursive skill invocation)
4. Prompt-craft auditor expanded to check for identity, rationalizations, and routing tables (8 rules instead of 5)

**Why it works:** Identity framing produces intrinsic behavior — the agent doesn't write code because it's not its job, not because a rule says don't. Named rationalizations intercept the reasoning chain before the action, which is cheaper and more reliable than intercepting the action itself.

**How to apply:** When diagnosing new behavioral issues, try identity framing and named rationalizations FIRST (tiers 1-2 in prompt-craft diagnose). Only escalate to prohibitions and restructuring if those don't hold.

**Verified:** User confirmed 2026-03-22. Only exception was CI infra failures (separately fixed via CI Fix Protocol PR #3).
