## Consolidated Rules (primary)

- [consolidated-feedback.md](consolidated-feedback.md) — All behavioral rules distilled into one file. Load this.

## Feedback History (not loaded by default)

- [feedback-plan-discovery.md](feedback-plan-discovery.md) — List docs/plans/ directory first when resuming work; never guess filenames
- [feedback-agent-laziness.md](feedback-agent-laziness.md) — Agents silently drop findings during planning and implementation; require completeness gates
- [feedback-main-agent-coding.md](feedback-main-agent-coding.md) — Main agent writes code directly in Phase 5 instead of spawning implementer teammates
- [feedback-agent-teams.md](feedback-agent-teams.md) — Agent teams when COORDINATION=yes (design, debugging 3+ hypotheses); subagents when independent work (execution, audit)
- [feedback-prompt-craft-usage.md](feedback-prompt-craft-usage.md) — Always use /prompt-craft audit before writing or modifying skill instructions, phase files, or agent prompts
- [feedback-symlinks.md](feedback-symlinks.md) — Update symlinks in ~/.claude/skills/ when renaming or creating standalone skills
- [feedback-dispatch-ordering.md](feedback-dispatch-ordering.md) — Dispatch agent work before self-executable tasks to maximize parallelism
- [feedback-ship-vs-release.md](feedback-ship-vs-release.md) — Always suggest /release not /ship; coding-team has its own equivalents for gstack skills
- [feedback-rationalization-bypass.md](feedback-rationalization-bypass.md) — CC invents "mechanical" exceptions to bypass the all-code-through-coding-team rule
- [feedback-size-rationalization-bypass.md](feedback-size-rationalization-bypass.md) — Main agent edits code directly by rationalizing individual fixes as "too small" for delegation
- [feedback-doc-level-edits-rationalization.md](feedback-doc-level-edits-rationalization.md) — Orchestrator classifies hook/phase/prompt files as "documentation" to bypass delegation
- [feedback-context-weight.md](feedback-context-weight.md) — SKILL.md and execution.md too heavy; memory files should consolidate; direct embedding > propagation
- [feedback-no-pause-between-phases.md](feedback-no-pause-between-phases.md) — Don't pause between severity phases in scan-fix workflows; auto-continue with progress summaries
- [feedback-ci-infra-failures.md](feedback-ci-infra-failures.md) — Agents waste cycles on non-code CI failures; added failure classification protocol
- [feedback-strategy-validation.md](feedback-strategy-validation.md) — Identity framing + named rationalizations confirmed working; zero friction since strategy change (2026-03-22)
- [feedback-test-coverage-attrition.md](feedback-test-coverage-attrition.md) — Agents claim "all hooks covered" while hooks remain uncovered; took 3 audit cycles despite explicit directives
- [feedback-partial-fix-still-active.md](feedback-partial-fix-still-active.md) — Harness-engineer offered to fix only P1s, silently dropping P2/P3; selective-fix rationalization persists
- [feedback-context-survival-gates.md](feedback-context-survival-gates.md) — QA review and second-opinion gates lost to context pressure in long sessions; fixed with mandatory post-execution checklist + codex review syntax fix
- [feedback-spec-clarity-rationalization.md](feedback-spec-clarity-rationalization.md) — Orchestrator offers self-execution when spec is clear; spec clarity determines model tier not delegation

## Project History (not loaded by default)

- [project-cycle14-audit-2026-03-26.md](project-cycle14-audit-2026-03-26.md) — Cycle 14: deploy drift critical, ENFORCEMENT_MAP 13→24, context survival gates, codex CLI fix
