# Reference Files

Loaded on demand by the skill router. Not needed during active phase work.

---

**Standalone skills** (can be invoked independently or from the pipeline):

| Skill | Path | Purpose |
|-------|------|---------|
| `/debug` | `skills/debug/SKILL.md` | Four-phase root cause investigation |
| `/verify` | `skills/verify/SKILL.md` | Evidence-before-claims gates |
| `/review-feedback` | `skills/review-feedback/SKILL.md` | How to handle review feedback |
| `/worktree` | `skills/worktree/SKILL.md` | Git worktree setup and cleanup |
| `/parallel-fix` | `skills/parallel-fix/SKILL.md` | Parallel agent dispatch for independent failures |
| `/tdd` | `skills/tdd/SKILL.md` | Test-driven development cycle |
| `/prompt-craft` | `skills/prompt-craft/SKILL.md` | Skill & prompt engineering, diagnosis, audit. For instruction text quality — not harness infrastructure. |
| `/harness-engineer` | `skills/harness-engineer/SKILL.md` | Harness infrastructure: hooks, rules, settings, constraint promotion, maturity assessment. For systems design — not instruction text. |
| `/second-opinion` | `skills/second-opinion/SKILL.md` | Cross-model second opinion via OpenAI Codex CLI |
| `/scope-lock` | `skills/scope-lock/SKILL.md` | Restrict edits to a directory during debugging |
| `/scope-unlock` | `skills/scope-unlock/SKILL.md` | Remove scope-lock edit restriction |
| `/release` | `skills/release/SKILL.md` | Automated release: sync, test, push, PR |
| `/retrospective` | `skills/retrospective/SKILL.md` | Post-ship engineering retrospective. **Always use this, not gstack's `/retro`.** |
| `/doc-sync` | `skills/doc-sync/SKILL.md` | Post-ship documentation update |

**Phase details** (loaded on demand by the active phase):

| Phase | File |
|-------|------|
| Session Resume | `phases/session-resume.md` |
| Dialogue | `phases/dialogue.md` |
| Design Team | `phases/design-team.md` |
| Spec Review | `phases/spec-review.md` |
| Planning | `phases/planning.md` |
| Execution | `phases/execution.md` |
| Post-Execution Review | `phases/post-execution-review.md` |
| Completion | `phases/completion.md` |

**Extracted on-demand files** (loaded by phase files when needed):

| File | Extracted from | Purpose |
|------|---------------|---------|
| `phases/audit-loop.md` | execution.md | Audit team dispatch, triage, and loop exit |
| `phases/design-team-lifecycle.md` | design-team.md | Agent teams lifecycle details |
| `phases/doc-drift-scan.md` | execution.md | Documentation drift scan |
| `phases/memory-nudge.md` | completion.md | Session learning extraction |
| `phases/plan-format.md` | planning.md | Plan document template and task structure |
| `phases/planning-next-steps.md` | planning.md | Risk signals and second-opinion gate |

**Agent definitions** (used by the execution loop):

| File | Purpose |
|------|---------|
| `agents/ct-implementer.md` | Implementer (task team member) prompt template |
| `agents/ct-spec-reviewer.md` | Spec compliance + TDD verification (read-only) |
| `agents/ct-simplify-auditor.md` | Simplify auditor — clarity and complexity (read-only) |
| `agents/ct-harden-auditor.md` | Harden auditor — security and resilience (read-only) |
| `agents/ct-prompt-craft-auditor.md` | Prompt-craft auditor — CC instruction quality (read-only, conditional) |
| `agents/ct-harness-engineer.md` | Harness engineer — hooks, rules, settings, constraint promotion, maturity (read-write for audit commands) |
| `agents/ct-spec-doc-reviewer.md` | Design doc reviewer template |
| `agents/ct-plan-doc-reviewer.md` | Plan doc reviewer template |
