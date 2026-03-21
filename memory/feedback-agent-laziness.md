---
name: Agent laziness — incomplete scan remediation
description: Agents drop findings during planning and implementation — plans cover only half the scan findings, implementers skip assigned tasks
type: feedback
---

Agents tend to silently drop work items. A scan with 20 findings produces a plan that only addresses 10. Implementers also skip tasks they were given.

**Why:** The user observed this pattern across multiple sessions. Partial remediation gives false confidence that a scan was fully addressed.

**How to apply:** Add explicit completeness gates in both the planning phase (every finding must be planned, deferred with rationale, or marked false positive — never silently dropped) and the execution phase (implementer must account for every task step, orchestrator must verify all tasks were completed before marking done).
