---
name: Context weight and propagation failures
description: SKILL.md and execution.md are too heavy; memory files should consolidate; direct embedding beats propagation through intermediaries
type: feedback
---

Four context engineering improvements needed:

1. **SKILL.md at 304 lines is too heavy for a root file.** The session router (Steps 0-3, context refresh, recovery heuristics) is ~160 lines loaded before the orchestrator starts the user's task. Move recovery heuristics (lines 56-143) to `phases/session-resume.md`, loaded only when continuation is detected.

2. **execution.md at 327 lines is the densest file.** Contains dispatch logic, audit loop, findings gate, Codex review, security escalation, and completion handoff — all loaded during highest context pressure (implementer + auditor prompts also in context). Move Codex/second-opinion integration to a separate `phases/post-execution-review.md`.

3. **Propagation failures are the dominant failure mode.** Cases 5, 8, 9, 18 all trace to instructions not reaching the right agent. The principle: direct embedding > propagation through intermediaries. Flatten structures where possible — put tools in worker descriptions, not Team Leader instructions.

4. **10 memory/feedback files compete for attention budget.** If all loaded at session start, they dilute the actual task. Consolidate into a single `memory/consolidated-feedback.md` with the key rules, refreshed periodically. Keep individual files for history but load only the consolidated version.

**Why:** Context window is a fixed resource. Every line loaded before the task starts is a line that can't be used for the task itself. Heavy root files, dense phase files, and scattered memory files all reduce effective context for the actual work.

**How to apply:** This is a refactoring task — route through `/coding-team` when ready. Prioritize: (1) memory consolidation (cheapest, immediate impact), (2) SKILL.md session-resume extraction, (3) execution.md Codex extraction.
