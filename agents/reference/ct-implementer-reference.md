# ct-implementer Reference

On-demand detail extracted from `agents/ct-implementer.md`. The dispatched implementer reads this when the pointers in its prompt reach these topics.

## Code Organization

- Follow the file structure defined in the plan
- Each file should have one clear responsibility
- If a file grows beyond the plan's intent, report as DONE_WITH_CONCERNS
- In existing codebases, follow established patterns

## When You're in Over Your Head

STOP and escalate with BLOCKED or NEEDS_CONTEXT status when the task requires decisions beyond your scope, or you've been reading files without progress. Read `~/.claude/skills/coding-team/agents/reference/implementer-reference.md` for escalation details.

## Before Reporting Back: Self-Review

**Completeness:** Count the items in the spec. Count the items you changed. Are they equal? If not, go back and finish.
**Quality:** Are names clear? Is the code clean and maintainable?
**Discipline:** Right-sized per `~/.claude/golden-principles.md` #17 (Right-Sized Code)?
**Testing:** Do tests verify behavior (not mock behavior)? Did I follow TDD?
**Documentation:** Did my changes affect any documented behavior? If so, did I update the docs?
**Reachability:** Is each new feature wired to ≥1 entry point (route/CLI/handler/test)? If not, flag "DARK FEATURE: {name}" — see `~/.claude/reference/dark-features.md`.

If you find issues during self-review, fix them now.
