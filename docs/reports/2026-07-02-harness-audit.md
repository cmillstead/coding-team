# Harness Audit — 2026-07-02

Full audit of the coding-team harness: entry layer/config, agents, commands, phases, cookbook, hooks (+tests/lint run), rules, sub-skills, memory, docs. Six parallel audit passes, findings cross-verified against the live filesystem.

**Ground truth runs:** pytest (hooks): 609 passed, 8 skipped, **134 failed + 49 errors — all from one root cause (F4)**. ruff (py files only): 51 violations, all cosmetic. Deploy parity: **zero drift** — all rules/agents/hooks in `~/.claude/` are live symlinks into this repo (one audit agent claimed deployment was broken; verified false and discarded).

## What's working well

The symlink deploy (`deploy.sh`) makes drift structurally impossible and self-verifies hook registration; `deploy-drift-check.py` re-verifies each session. `phases/task-weight.md` is a genuinely strong single-source-of-truth tier ladder, consistently deferred to by every downstream gate. Named-rationalizations discipline is load-bearing and uniformly applied across agents, phases, and memory. Dispatcher fault isolation is well-engineered (one broken handler can't block tool calls) and the two blocking guards (`write-guard`, `git-safety-guard`) fail closed with tracebacks. Progressive disclosure (reference-file extraction, on-demand loads) is real. The codex-learnings graduation system in `/second-opinion` is a working self-improvement loop. Agent contracts (dispatch context, BLOCKED escape hatch, finding integrity, MCP fallback) are consistent across all 17 agents, and model routing matches the CLAUDE.md table exactly.

## Findings

### P1 — Broken / contradictory

| # | Finding | Evidence | Fix |
|---|---------|----------|-----|
| F1 | **Stale pipeline fork.** `cookbook/phases/` (18 files) + `commands/build.md` are a frozen pre-tier-gating copy of `phases/`. `/build` runs the old pipeline: no tier gating, the exact QA-skip rule (`1 task AND ≤3 files`) that `phases/execution-reminders.md:74` names as a rationalization to reject, old agent names, "second-opinion NEVER skip" contradicting the tier matrix. README has causality backwards: calls `build.md` "primary orchestrator" (README:16) and labels `phases/` "legacy (mirrors cookbook/phases/)" (README:467) — git history shows the opposite. | diff `phases/dialogue.md` vs cookbook twin (24 lines); `completion.md` twins (144 lines); `commands/build.md:148-245` | Port any unique cookbook improvements into `phases/`, delete `cookbook/phases/` + `cookbook/references/`, rewrite `commands/build.md` as a thin wrapper over SKILL.md+`phases/`, fix README |
| F2 | **6 dead agents, deployed live.** `ct-builder`, `ct-reviewer`, `ct-qa`, `ct-harden-reviewer`, `ct-plan-reviewer`, `ct-prompt-reviewer` have zero references in `phases/` (only the dead cookbook tree) yet are symlinked into `~/.claude/agents/` — near-identical stale twins of live agents that will silently drift and can be mis-dispatched. | grep `phases/` for each name: 0 hits; `~/.claude/agents/ct-builder.md` symlink exists | Diff each against live counterpart for unported improvements, then delete all 6 + their deploy symlinks |
| F3 | **`loop-detection.py` is non-functional.** Reads `tool_result` (loop-detection.py:142); real PostToolUse key is `tool_response` (per `_lib/event.py:31-35`). The 3-retry loop-breaking documented in golden-principles #8 (accurately, as broken) and README:419 / SKILL.md Red Flags (as working) never fires. | `event.get("tool_result", {})` never matches | One-line fix: use `_lib.event.get_tool_result()` like every other hook; add regression test |
| F4 | **Hook test suite not portable.** `HOOKS_DIR = Path("/Users/cevin/.claude/skills/coding-team/hooks")` hardcoded in `conftest.py` + 14 test files → 134 failures/49 errors anywhere but that literal path (CI, other machine, moved checkout). `test_git_safety_guard.py:13` already has the correct pattern. | pytest run in sandbox | Replace with `Path(__file__).resolve().parent.parent` in all 15 files |
| F5 | **`prompts/*.md` referenced in ~7 phase files; directory doesn't exist.** Pattern gates PROMPT_CRAFT_ADVISORY dispatch, risk-signal classification, write-guard routing — silently no-ops for that slice. | `named-rationalizations.md:21,30`, `execution.md:23,183`, `task-weight.md:35`, `planning.md:25`, `planning-next-steps.md:12`, `audit-loop.md:17` | Remove `prompts/*.md` from pattern lists (or create the directory if intended) |
| F6 | **Nonexistent `Teammate` tool used in two skills.** `debug/SKILL.md:89,115` and `parallel-fix/SKILL.md:67,89,91` use `Teammate({...})`; SKILL.md:23 and `prompt-craft/language-rules.md:19` explicitly name this as the known anti-pattern (silently fails → fallback path). README architecture prose also describes `Teammate` as real. | as cited | Rewrite call sites to `TeamCreate`/`Agent({team_name})`/`TaskCreate`/`SendMessage`; fix README prose |

### P2 — Drift / staleness / gaps

| # | Finding | Fix |
|---|---------|-----|
| F7 | **`commands/*.md` ↔ `skills/*/SKILL.md` duplication for ~15 paired skills.** 6 byte-identical, 9 already drifted (`second-opinion` diverges by 159 lines; `doc-sync` command missing "When to Use"). No canonical side declared. | Declare `skills/` canonical; make `commands/*.md` thin pointer stubs (or generate at deploy time) |
| F8 | **`phases/reference-files.md` (the designated authoritative index) is stale.** Missing 7 skills (`/doc-write`, `/dep-audit`, `/migration-guide`, `/onboard`, `/a11y`, `/api-qa`, `/incident`), missing `ct-qa-reviewer` from agent table, missing `task-weight.md` + `named-rationalizations.md` from on-demand table. | Regenerate; see R2 (index-verifier script) |
| F9 | **README structural drift.** `rules/` block lists 5 files that live in `~/.claude/rules-on-demand/` (external, not repo — a fresh clone silently lacks them); hooks block omits the 4 dispatchers (the actual settings.json entry points), `ci-orphan-detector.sh`, 3 `_lib` modules; memory count says ~34, actual 42. | Rewrite README file-structure + hooks sections; document `rules-on-demand/` as an external prerequisite |
| F10 | **Memory frozen at 2026-03-27; ~3 months of major work unrecorded.** No decision records for: submodule migration, deploy.sh copy→symlink rewrite (existing decision record describes the *old* copy mechanism), dispatcher consolidation, task-weight ladder. Hook-accumulation memory counts a unit ("hook") that no longer exists. Moratorium "until 2026-04-09" never resolved. 9 pre-April project-* files undistinguished from current state. | Write June decision records; addendum on the deploy decision; archive pre-April project-* files to `memory/archive/`; add "as of" date to MEMORY.md |
| F11 | **Crash-guard inconsistency in hooks.** 5 hooks (`codesight-hooks`, `lint-warning-enforcer`, `coding-team-lifecycle`, `loop-detection`, `hook-health-check`) lack top-level try/except; dispatchers treat rc=1 (crash) same as "nothing to say" — a crashed check silently stops protecting between health-check probes. | Add standard crash-guard wrapper; dispatcher logs advisory on rc not in (0,2) |
| F12 | **WCAG drift.** `config/CLAUDE.md:194` says 2.2 AA; `phases/agent-standards.md:18` (extracted *from* CLAUDE.md) says 2.1 AA. | Update agent-standards.md to 2.2 |
| F13 | **Dead pointer in failure taxonomy.** `~/.claude/rules-on-demand/failure-taxonomy.md:54` → `phases/edit-routing.md` (doesn't exist; content lives in SKILL.md:173-186). | Repoint |
| F14 | **Undocumented external dependencies.** gstack commands (`/scan-security`, `/ship`, `/freeze`, `/document-release`…) referenced by 8+ skills; `engram` CLI assumed on PATH by harness-engineer with no fallback; `rules-on-demand/` (F9). | "External prerequisites" section in README + engram fallback line |
| F15 | **Dangling in-flight work.** `docs/handoff/2026-06-20-workflow-api-spike-RESUME.md` + D199 still `pending` with no resolution trace; 27 files in `docs/plans/` with no status index (feedback-plan-discovery tells agents to `ls` it). | Resolve/mark the handoff; add `docs/plans/INDEX.md` or `archive/` split |

### P3 — Polish

| # | Finding | Fix |
|---|---------|-----|
| F16 | ruff: 51 violations (2 genuinely dead imports; rest cosmetic); `ruff check .` from root chokes on `deploy.sh`; pytest not runnable from root | `ruff --fix` the real ones; root `pyproject.toml` with excludes; `__all__` in `_lib/__init__.py` |
| F17 | ~15-20 lines of verbatim boilerplate (MCP fallback, Finding Integrity, BLOCKED protocol) duplicated across 8-9 agents; several files at/over the self-imposed 200-line threshold (`debug` 200, `second-opinion` 200, `ct-builder` 207, `ct-implementer` 206) | Factor into shared rules files; extract `debug` Phase-2 tables to reference file |
| F18 | `.harness-verified`: 0-byte orphan, zero references repo-wide | Delete or document |
| F19 | `agents/` mixes 2 reference docs with dispatchable personas; glob over-counts | Move to `agents/reference/` |
| F20 | `/a11y`, `/api-qa` missing from CLAUDE.md Proactive Skill Suggestions; 4 skills lack command stubs (`harness-engineer`, `doc-write`, `debug`, `prompt-craft`) | Add rows + stubs |
| F21 | SKILL.md:160 restates `rules/hook-bypass.md` verbatim (rule IS deployed/auto-loaded — duplication, not darkness); `hook-bypass`/`mcp-resilience` lack frontmatter unlike glob-scoped siblings | Replace inline copy with pointer; add explicit `alwaysApply` frontmatter |
| F22 | `completion.md` (268 lines) wiki-generation block (~85 lines) is fully tier-gated but always loaded | Extract to `phases/wiki-generation.md` on-demand |

## Recommendations (beyond direct fixes)

- **R1**: Resolve the fork (F1+F2+F6 README fixes) as one atomic cleanup — highest-leverage change in this audit.
- **R2**: Add `scripts/check-indexes.py` + CI step: verify every `agents/*.md` (non-reference) is referenced from `phases/`+SKILL.md, `reference-files.md` tables match globs, no dead path references (`prompts/`, deleted agent names), README file-structure matches `find`. Would have caught F1, F2, F5, F8, F9 mechanically. The harness enforces exactly this discipline on target codebases; it should run it on itself.
- **R3**: Run hook tests in CI from a non-`/Users/cevin` path so F4's class can't regress.
- **R4**: Memory freshness contract: MEMORY.md "as of" date + session-start rule to skim `docs/handoff/` when newest handoff postdates newest memory entry.

## Verification note

Finding "deployment not in effect" (one audit agent's P1) was cross-checked against the live filesystem and is **false** — all coding-team rules/agents/hooks are correctly symlinked in `~/.claude/`. Discarded.
