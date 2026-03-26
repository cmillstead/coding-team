---
name: Post-execution gates lost to context pressure
description: QA review and second-opinion gates get compacted out in long sessions (45+ tasks); fixed with mandatory post-execution checklist in execution-reminders.md
type: feedback
---

In long sessions (45 tasks, 5 batches), the Feature-Level QA Review and second-opinion gate instructions get compacted out of the context window. The orchestrator completes all tasks and jumps straight to Phase 6, skipping both mandatory gates.

**Why:** The QA step (execution.md:150) and second-opinion gate (post-execution-review.md) are loaded at Phase 5 start. By the time 45 tasks complete, those sections have been pushed out of context. The mid-phase reminders (every 3 tasks) didn't mention either step.

**How to apply:** execution-reminders.md now has a "Post-Execution Checklist" section that fires after the last task. execution.md has an explicit trigger to load it at the plan-completeness-verification step. The checklist names 4 rationalizations the orchestrator uses to skip these gates.

Also fixed: `codex review --base main "PROMPT"` is invalid — `--base` and `[PROMPT]` are mutually exclusive in the Codex CLI. Use `codex review --base main` without a prompt argument.
