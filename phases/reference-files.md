# Reference Files

Loaded on demand by the skill router. Not needed during active phase work.

---

**Standalone skills** (can be invoked independently or from the pipeline):

| Skill | Path | Purpose |
|-------|------|---------|
| `/a11y` | `skills/a11y/SKILL.md` | WCAG 2.2 AA source code audit — semantic markup, ARIA, keyboard nav, contrast, focus |
| `/api-qa` | `skills/api-qa/SKILL.md` | API endpoint testing — contract compliance, error handling, security, performance |
| `/debug` | `skills/debug/SKILL.md` | Four-phase root cause investigation |
| `/dep-audit` | `skills/dep-audit/SKILL.md` | Dependency audit — staleness, license risk, upgrade paths, health |
| `/doc-sync` | `skills/doc-sync/SKILL.md` | Post-ship documentation update |
| `/doc-write` | `skills/doc-write/SKILL.md` | Write or improve documentation from scratch — README, ARCHITECTURE, API references, tutorials |
| `/harness-engineer` | `skills/harness-engineer/SKILL.md` | Harness infrastructure: hooks, rules, settings, constraint promotion, maturity assessment. For systems design — not instruction text. |
| `/incident` | `skills/incident/SKILL.md` | Production incident coordination, response process design, post-mortems |
| `/migration-guide` | `skills/migration-guide/SKILL.md` | Write upgrade/migration guides for breaking changes |
| `/onboard` | `skills/onboard/SKILL.md` | Guided orientation to an unfamiliar codebase |
| `/parallel-fix` | `skills/parallel-fix/SKILL.md` | Parallel agent dispatch for independent failures |
| `/prompt-craft` | `skills/prompt-craft/SKILL.md` | Skill & prompt engineering, diagnosis, audit. For instruction text quality — not harness infrastructure. |
| `/release` | `skills/release/SKILL.md` | Automated release: sync, test, push, PR |
| `/retrospective` | `skills/retrospective/SKILL.md` | Post-ship engineering retrospective. **Always use this, not gstack's `/retro`.** |
| `/review-feedback` | `skills/review-feedback/SKILL.md` | How to handle review feedback |
| `/scope-lock` | `skills/scope-lock/SKILL.md` | Restrict edits to a directory during debugging |
| `/scope-unlock` | `skills/scope-unlock/SKILL.md` | Remove scope-lock edit restriction |
| `/second-opinion` | `skills/second-opinion/SKILL.md` | Cross-model second opinion via OpenAI Codex CLI |
| `/tdd` | `skills/tdd/SKILL.md` | Test-driven development cycle |
| `/verify` | `skills/verify/SKILL.md` | Evidence-before-claims gates |
| `/worktree` | `skills/worktree/SKILL.md` | Git worktree setup and cleanup |

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
| `phases/design-team-context-retrieval.md` | design-team.md | Episode & context retrieval for design workers |
| `phases/reference-files.md` | SKILL.md | Standalone skills, phase details, on-demand files, agent definitions |
| `phases/agent-standards.md` | global CLAUDE.md (moved 2026-05-20) | Model routing tiers + UI/UX standards for dispatched agents |
| `phases/task-weight.md` | SKILL.md / referenced by all gates | Single source of truth for task tier classification and per-tier gate matrix |
| `phases/named-rationalizations.md` | cross-phase | Coding-team-specific known rationalizations, cross-referencing the global failure taxonomy |
| `phases/wiki-generation.md` | completion.md | Tier-gated vault wiki article generation |
| `agents/implementer-reference.md` | ct-implementer.md | Code exploration, CI fix context, escalation guidance |
| `agents/harness-engineer-reference.md` | ct-harness-engineer.md | Report template, Phase 5 auditor protocol, hook design protocol |

**Agent definitions** (used by the execution loop):

| File | Purpose |
|------|---------|
| `agents/ct-implementer.md` | Implementer (task team member) — writes code, tests, and commits using TDD discipline |
| `agents/ct-spec-reviewer.md` | Spec compliance + TDD verification (read-only) |
| `agents/ct-simplify-auditor.md` | Simplify auditor — unnecessary complexity, dead code, naming issues (read-only) |
| `agents/ct-harden-auditor.md` | Harden auditor — security vulnerabilities, resilience gaps, dependency risks (needs Bash) |
| `agents/ct-qa-reviewer.md` | Feature-level QA review after all tasks complete — integration, edge cases, dark features, test coverage gaps (read-only) |
| `agents/ct-prompt-craft-auditor.md` | Prompt-craft auditor — CC instruction quality (read-only, conditional) |
| `agents/ct-harness-engineer.md` | Harness engineer — hooks, rules, settings, constraint promotion, maturity (read-write for audit commands) |
| `agents/ct-spec-doc-reviewer.md` | Design doc reviewer — completeness, consistency, readiness for planning (read-only) |
| `agents/ct-plan-doc-reviewer.md` | Plan doc reviewer — completeness, spec alignment, task decomposition, finding coverage (read-only) |
