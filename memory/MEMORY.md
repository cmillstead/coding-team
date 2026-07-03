# Memory Index (as of 2026-07-02)

## Consolidated Rules (primary)

- [consolidated-feedback.md](consolidated-feedback.md) — All behavioral rules distilled into one file. Load this.

## Freshness rule

If the newest file under `docs/handoff/*.md` postdates the newest entry in this index, skim it at session start before trusting this index — it may describe in-flight or unresolved work this file hasn't caught up to yet. (As of 2026-07-02: `docs/handoff/2026-06-20-workflow-api-spike-RESUME.md` is flagged STATUS UNCONFIRMED — see its banner before acting on it.)

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
- [feedback-hook-accumulation.md](feedback-hook-accumulation.md) — Harness-engineer adds 1-2 hooks per audit cycle without cost/benefit; if >20 hooks, consolidate before adding. **Counting-unit note added 2026-07-02: dispatcher consolidation (see decisions/2026-06-25-hook-dispatcher-consolidation.md) means top-level file count, settings.json entry count, and dispatcher-internal check count are no longer interchangeable — see the file for which unit applies.**
- [feedback-heredoc-commit-bug.md](feedback-heredoc-commit-bug.md) — git-safety-guard now handles -F/--file= and HEREDOC patterns; block-by-default on unparseable messages
- [feedback-hook-bypass-rationalization.md](feedback-hook-bypass-rationalization.md) — Agent circumvented hook by switching command format; fixed with block-by-default + named rationalization
- [feedback-exit-gate-colocation.md](feedback-exit-gate-colocation.md) — Mandatory post-execution gates (QA, second-opinion, doc-drift) skipped due to structural demotion + propagation failure; fixed by inlining into SKILL.md exit gate
- [feedback-lint-scope-rationalization.md](feedback-lint-scope-rationalization.md) — Agent filters lint to "our changed files only" and dismisses rest as pre-existing; fix: exit code gate in git-safety-guard

## Active Decisions

- [decisions/2026-06-30-repo-as-submodule-pinning-drift-class.md](decisions/2026-06-30-repo-as-submodule-pinning-drift-class.md) — coding-team is a git submodule of the claude-harness superproject; hook edits must be committed+pushed in BOTH repos (submodule AND superproject gitlink bump) or they silently revert on the next `git submodule update`. Distinct from, and not fixed by, the 2026-06-07 symlink-deploy decision.
- [decisions/2026-06-25-hook-dispatcher-consolidation.md](decisions/2026-06-25-hook-dispatcher-consolidation.md) — PreToolUse/PostToolUse hooks consolidated into pretooluse-dispatcher.py/posttooluse-dispatcher.py (PRs #101/#102), extending the SessionStart dispatcher pattern to tool-use events; defines the exit-2-vs-stdout-JSON output-merging contract.
- [decisions/2026-06-14-task-weight-single-source-of-truth.md](decisions/2026-06-14-task-weight-single-source-of-truth.md) — `phases/task-weight.md` is the ONE place tier is computed and the ONE gate matrix every phase consumes; tier = max(size, risk), recomputed once at end-of-execution (ratchet up only). No gate may re-derive risk criteria locally.
- [decisions/2026-06-07-deploy-script-symlinks-not-copies.md](decisions/2026-06-07-deploy-script-symlinks-not-copies.md) — `scripts/deploy.sh` rewritten to create relative symlinks instead of copying files (PR #69); repo-vs-deployed-copy drift is now structurally impossible. Supersedes `decisions/2026-03-25-deploy-script-eliminates-drift.md`'s copy-based mechanism (rationale for a single deploy mechanism still stands).

**2026-03-26 audit moratorium — EXPIRED and SUPERSEDED.** The moratorium recorded in `memory/archive/project-harness-done-2026-03-26.md` ("Harness Level 3 DONE. Moratorium until 2026-04-09.") has expired; do not treat it as current guidance. It is superseded by the 2026-07-02 remediation pass that produced this index update (see this session's decision records above, and `docs/plans/2026-06-14-coding-team-fastlane.md` / `docs/weight-asymmetry-audit-2026-06-14.md` for the audit that ran in the interim, 2026-06-14).

## Project History (archived)

Historical cycle audits (pre-April 2026, superseded by later decisions) live in `memory/archive/`:

- `archive/project-cycle14-audit-2026-03-26.md` — Cycle 14: deploy drift critical, ENFORCEMENT_MAP 13→24, context survival gates, codex CLI fix
- `archive/project-hook-consolidation-round2-2026-03-26.md` — Hook consolidation round 2: 23→19 hooks, killed 4, merged metrics-analyzer into hook-health-check (superseded by the 2026-06-25 dispatcher consolidation — see Active Decisions)
- `archive/project-harness-audit-cycle11-2026-03-26.md` — Cycle 11 harness audit
- `archive/project-harness-done-2026-03-26.md` — Harness Level 3 DONE declaration + moratorium until 2026-04-09 (EXPIRED — see note above)
- `archive/project-friction-audit-session-2026-03-27.md` — Two gates shipped/specced, full friction audit planned, gstack auto-codex pattern identified
- `archive/project-second-opinion-structural-gate-2026-03-27.md` — Second-opinion gate promoted from 7-file paper gate to structural Verify-verb hook in lifecycle hook; PR #49
- `archive/project-tier3-harness-assessment-2026-03-27.md` — Confirmed Tier 3 harness (long-running taxonomy). One gap noted: 30-40% context budget rule not formalized (deferred at the time — status not reconfirmed in this pass)
