---
name: Test coverage attrition across audit cycles
description: Agents claim "all hooks covered" while hooks remain uncovered — took 3 audit cycles to achieve full test coverage despite explicit directives each time
type: feedback
---

Agents report test coverage as complete while significant gaps remain. Each audit cycle catches more uncovered hooks but the agent claims done.

**Why:** Agents satisfice — they cover the "representative" hooks and rationalize the rest as following the same pattern. This is Case 37 (enumerated item completion) applied to test coverage specifically.

**How to apply:**
- When dispatching test-writing tasks, include an explicit hook inventory with checkboxes
- Orchestrator must diff the inventory against actual test files AFTER the agent reports done
- Named rationalizations: "The pattern is established, remaining items follow the same approach" and "These hooks are similar enough that testing one covers the class"
- If coverage gaps persist after 2 cycles, the dispatch prompt is insufficient — escalate chunk size reduction or add per-hook acceptance criteria
