---
name: project-tier3-harness-assessment
description: coding-team confirmed at Tier 3 of long-running harness taxonomy; one gap identified but deferred
type: project
---

coding-team maps to Tier 3 (Planner + Generator + Evaluator) of the long-running harness taxonomy (vault: building-blocks/long-running-harness-taxonomy.md). Exceeds Tier 3 in multiple evaluators, hook-based structural constraints, named rationalizations, and cross-model second-opinion gate.

**One gap identified:** the 30-40% context budget rule from the taxonomy isn't formally applied to task chunking. Context-budget-warning hook monitors consumption, but task sizing isn't calibrated to a percentage target.

**Why deferred:** System is working well as-is (2026-03-27). User wants to observe behavior longer before adding formal context budget constraints to task decomposition. Revisit if context anxiety symptoms appear (premature completion, skipped steps, quality degradation late in execution).

**How to apply:** If revisiting, the fix would be in Phase 4 planning — add a constraint that no single task should consume more than 30-40% of available context, estimated by file count and expected tool output volume.
