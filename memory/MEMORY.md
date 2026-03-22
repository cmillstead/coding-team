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
- [feedback-context-weight.md](feedback-context-weight.md) — SKILL.md and execution.md too heavy; memory files should consolidate; direct embedding > propagation
