# Reference Files

Loaded on demand by the skill router. Not needed during active phase work.

---

**Standalone skills** (can be invoked independently or from the pipeline):

| Skill | Path | Purpose |
|-------|------|---------|
| `/debug` | `skills/debug/SKILL.md` | Four-phase root cause investigation |
| `/verify` | `commands/verify.md` | Evidence-before-claims gates |
| `/review-feedback` | `commands/review-feedback.md` | How to handle review feedback |
| `/worktree` | `skills/worktree/SKILL.md` | Git worktree setup and cleanup |
| `/parallel-fix` | `commands/parallel-fix.md` | Parallel agent dispatch for independent failures |
| `/tdd` | `skills/tdd/SKILL.md` | Test-driven development cycle |
| `/prompt-craft` | `skills/prompt-craft/SKILL.md` | Skill & prompt engineering, diagnosis, audit. For instruction text quality — not harness infrastructure. |
| `/harness-engineer` | `skills/harness-engineer/SKILL.md` | Harness infrastructure: hooks, rules, settings, constraint promotion, maturity assessment. For systems design — not instruction text. |
| `/second-opinion` | `skills/second-opinion/SKILL.md` | Cross-model second opinion via OpenAI Codex CLI |
| `/scope-lock` | `skills/scope-lock/SKILL.md` | Restrict edits to a directory during debugging |
| `/scope-unlock` | `skills/scope-unlock/SKILL.md` | Remove scope-lock edit restriction |
| `/release` | `commands/release.md` | Automated release: sync, test, push, PR |
| `/retrospective` | `skills/retrospective/SKILL.md` | Post-ship engineering retrospective. **Always use this, not gstack's `/retro`.** |
| `/doc-sync` | `skills/doc-sync/SKILL.md` | Post-ship documentation update |

**Phase details** (loaded on demand by the active phase):

| Phase | File |
|-------|------|
| Session Resume | `cookbook/phases/session-resume.md` |
| Dialogue | `cookbook/phases/dialogue.md` |
| Design Team | `cookbook/phases/design-team.md` |
| Spec Review | `cookbook/phases/spec-review.md` |
| Planning | `cookbook/phases/planning.md` |
| Execution | `cookbook/phases/execution.md` |
| Post-Execution Review | `cookbook/phases/post-execution-review.md` |
| Completion | `cookbook/phases/completion.md` |

**Extracted on-demand files** (loaded by phase files when needed):

| File | Extracted from | Purpose |
|------|---------------|---------|
| `cookbook/phases/audit-loop.md` | execution.md | Audit team dispatch, triage, and loop exit |
| `cookbook/phases/design-team-lifecycle.md` | design-team.md | Agent teams lifecycle details |
| `cookbook/phases/doc-drift-scan.md` | execution.md | Documentation drift scan |
| `cookbook/phases/memory-nudge.md` | completion.md | Session learning extraction |
| `cookbook/phases/plan-format.md` | planning.md | Plan document template and task structure |
| `cookbook/phases/planning-next-steps.md` | planning.md | Risk signals and second-opinion gate |
| `cookbook/phases/design-team-context-retrieval.md` | design-team.md | Episode & context retrieval for design workers |
| `cookbook/phases/reference-files.md` | SKILL.md | Standalone skills, phase details, on-demand files, agent definitions |
| `cookbook/references/builder-reference.md` | ct-builder.md | Code exploration, CI fix context, escalation guidance |
| `agents/harness-engineer-reference.md` | ct-harness-engineer.md | Report template, Phase 5 auditor protocol, hook design protocol |

**Agent definitions** (used by the execution loop):

| File | Purpose |
|------|---------|
| `agents/ct-builder.md` | Implementer (task team member) prompt template |
| `agents/ct-reviewer.md` | Spec compliance + TDD verification (read-only) |
| `agents/ct-reviewer.md` | Simplify auditor — clarity and complexity (read-only) |
| `agents/ct-harden-reviewer.md` | Harden auditor — security and resilience (read-only) |
| `agents/ct-prompt-reviewer.md` | Prompt-craft auditor — CC instruction quality (read-only, conditional) |
| `agents/ct-harness-engineer.md` | Harness engineer — hooks, rules, settings, constraint promotion, maturity (read-write for audit commands) |
| `agents/ct-plan-reviewer.md` | Design doc reviewer template |
| `agents/ct-plan-reviewer.md` | Plan doc reviewer template |
