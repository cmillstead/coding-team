---
name: Agent laziness — incomplete scan remediation
description: Agents drop findings during planning and implementation — plans cover only half the scan findings, implementers skip assigned tasks
type: feedback
---

Agents tend to silently drop work items. A scan with 8 findings produces a plan that only addresses 4. This persisted across multiple fix attempts because the enforcement was self-referential — the planning worker was asked to self-check completeness, which LLMs are bad at.

**Why:** Three root causes identified:
1. Planning worker (subagent) may not receive the full Completeness Gate instructions — they're deep in a long file
2. Plan-doc-reviewer had no instruction to validate finding coverage
3. The completeness check was self-policing (planning worker checks itself) with no external verification

**How to apply:** Fixed via two structural changes:
1. **Pre-flight count** (planning.md): The orchestrator counts input findings BEFORE dispatching the planning worker and passes `**Input findings: N**` + a numbered list as a hard target. The worker cannot silently reduce the count.
2. **Reviewer enforcement** (plan-doc-reviewer.md): The plan-doc-reviewer now has a MANDATORY "Traceability Audit" as its first check — counts traceability table rows against the header count. Mismatch = blocking rejection.

The key insight: completeness checks must be done by a different agent than the one producing the output. Self-checks don't work for LLMs.
