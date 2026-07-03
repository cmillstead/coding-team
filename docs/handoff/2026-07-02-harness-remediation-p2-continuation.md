# Handoff: Harness Remediation — P2 fixes + ship (continuation)

**Continuation of** `docs/handoff/2026-07-02-harness-remediation-handoff.md`. That handoff's verify+ship tasks are largely DONE (see below); this file supersedes it for what remains. In-repo handoff: if you are Claude Code in this repo, resume from here.

Repo: `/Users/cevin/.claude/skills/coding-team` (this dir IS the live coding-team skill — files under `skills/`, `phases/`, `agents/`, `commands/` run in-place; only `hooks/`, and the deployed `agents/`/`rules/`/`commands/` symlinks, go through `scripts/deploy.sh`).
Branch: `fix/harness-audit-2026-07-02`. Working tree was clean at handoff.

## What's already DONE this session (do NOT redo)

1. **Hook test suite is GREEN on this machine:** `cd hooks && python3 -m pytest tests/ -k "not llm_eval and not llm_judge" -q` → **884 passed, 0 failed, 2 skipped** (the 2 skips are the known-acceptable `test_agent_smoke.py` "Not a read-only auditor" conditional skips). `test_prompt_dispatcher.py` passes here (`~/src/engram/.base/hooks` exists).
2. **Bug fixed — ci-orphan-detector latency (commit `86d02c7`):** the original `hooks/ci-orphan-detector.sh` stale-branch loop made one `gh pr list --head` network call PER stale local branch; with ~20 stale branches it exceeded the 15s test bound (`test_ci_orphan_detector.py::test_exits_cleanly_with_empty_input`) and slowed every session start (the hook is live via `session-start-dispatcher.py:77`). Fixed: fetch all open-PR head refs ONCE before the loop, local `grep -qxF` membership check. Test now passes.
3. **Bug fixed — duplicate C23 codex-learning IDs (commit `25257d1`), found by Codex second-opinion:** three new entries were all headed `# C23` (`...a35d-role-migration...`, `...19b2-early-return...`, `...0bb9-whole-object-pin...`), so `build-digest.py --check` failed (exit 3, "DUPLICATE ID C23") and would block every future commit via the git-safety-guard inline digest gate. Reassigned: a35d KEEPS C23; 19b2→C25; 0bb9→C26 (C24 was already taken by `...0f84-dedup...`). Regenerated `skills/second-opinion/codex-learnings-digest.md`. Verified: `python3 skills/second-opinion/scripts/build-digest.py --check` exits 0; `skills/second-opinion/scripts/test_build_digest.py` → 23 passed.
4. **Second-opinion (Codex) review RAN** against `dffa7db..HEAD` (the remediation diff). Verdict was REVISE: 1 P1 (fixed, #3 above) + 3 P2s (below, NOT yet done). Telemetry (`harness codex --log`) was NOT emitted — the `harness` CLI is not on PATH here (observability only; does not affect the review).

## Commits on the branch (newest first)
- `25257d1` fix: resolve duplicate C23 codex-learning IDs (C25/C26) and regenerate digest
- `86d02c7` fix: bound ci-orphan-detector stale-branch PR lookups to a single gh call
- `a9e920d` docs: handoff for finishing the 2026-07-02 remediation
- `e76ef75` … (and the original 22-finding remediation commits down to `6ada6b7`)
- Base `dffa7db` (tip of local-only `feat/paul-apply-review-gate`; NOT in origin/main — see PR base below)

## DECISIONS made by the user (final — execute, do not relitigate)
- **Fix ALL THREE P2s** before shipping (user chose "fix all three").
- **PR base = `main`.** The branch carries `dffa7db` ("emit modern permissionDecision allow shape in output.allow()"), tip of local-only `feat/paul-apply-review-gate`, not in origin/main — so PR-ing into main lands that commit too. User confirmed that's acceptable (Decision 2 = option 1). Do NOT rebase to drop dffa7db; do NOT force-push; do NOT merge directly to main.

## REMAINING WORK — resume via /coding-team

### The 3 P2 fixes (Codex second-opinion findings)

IMPORTANT nuance before you "fix" P2a/P2b: at review time these were assessed as **likely-mitigated, not confirmed-broken** — so step 0 for each is to VERIFY the actual path-resolution behavior. If a "fix" would hardcode a path that's actually resolved correctly today, the correct outcome may be "confirm + document the convention," not a rewrite. Do NOT blindly hardcode absolute paths without first establishing the right convention. This is a genuine design decision → route through /coding-team (Phase 4 design of the path convention, then Phase 5 implement), not a blind edit.

- **P2c — `scripts/deploy.sh` never prunes deleted agents (most clearly real).** The deploy loop (~`scripts/deploy.sh:60-62`) symlinks current `agents/ct-*.md` but never removes symlinks for deleted agents. This branch deleted 6 agents: `ct-builder`, `ct-reviewer`, `ct-qa`, `ct-harden-reviewer`, `ct-plan-reviewer`, `ct-prompt-reviewer`. Their symlinks were already removed BY HAND on this machine (per the original handoff), so THIS install is clean — but a deploy on any other install leaves stale/broken agent symlinks. Fix: add a reconcile/prune step to deploy.sh (remove `~/.claude/agents/ct-*.md` symlinks whose source `agents/<name>.md` no longer exists). This is a `hooks/scripts` change → Agent tool; MUST re-run `bash scripts/deploy.sh` after (expect "All hooks registered.") and add/adjust a test under `hooks/tests/` (there are existing deploy tests: `test_deploy_symlinks.py`, `test_deploy_drift_check.py`). Matches case-study #14 "infrastructure orphan."
- **P2a — command stubs delegate via relative path.** This branch rewrote many `commands/*.md` to thin stubs ("Read and follow `skills/<x>/SKILL.md`"). Codex: relative path may not resolve when the command is invoked as a standalone slash command from a user's project (cwd ≠ skill base dir). Assessment: probably fine (the runtime supplies the skill base dir — this session showed "Base directory for this skill: /Users/cevin/.claude/skills/coding-team" on `/coding-team`), but softer than absolute. Step 0: confirm how command→skill resolution actually works. If a change is warranted, apply the correct convention consistently across ALL affected command stubs (release, scope-lock, scope-unlock, debug, doc-write, harness-engineer, prompt-craft, + any other `commands/*.md` using `Read and follow skills/...`). Instruction files → Agent tool, PROMPT_CRAFT_ADVISORY.
- **P2b — agent prompts reference extracted `rules/*.md` relatively.** F17 factored boilerplate (finding-integrity, BLOCKED, MCP-fallback) into `rules/finding-integrity.md`, `rules/codesight-fallback.md`, `rules/mcp-resilience.md`, `rules/hook-bypass.md`; agents (e.g. `agents/ct-harden-auditor.md:104`) now reference them relatively. Codex: won't resolve when the agent is dispatched in a target repo. Assessment: mitigated TODAY because those rule files' CONTENT is injected globally via `config/CLAUDE.md` (subagents inherit it) — but that coupling is implicit and breaks on a fresh install without the injection. Step 0: confirm the injection covers every referenced rule. If a change is warranted, point agents at the deployed absolute path (rules deploy to `~/.claude/rules/`) or inline the content on dispatch — consistently across every ct-* agent that references an extracted rule. Instruction files → Agent tool, PROMPT_CRAFT_ADVISORY.

### After the P2 fixes — verify, then ship
1. Re-run the full hook suite (green), `build-digest.py --check` (exit 0), `bash scripts/deploy.sh` (ends "All hooks registered."), `python3 scripts/check-indexes.py` (all checks passed).
2. Consider a second `/second-opinion review` on the NEW P2 changes (the earlier review covered `dffa7db..HEAD` before these fixes).
3. **Open the PR** from `fix/harness-audit-2026-07-02` into **`main`** (base decision above). PR description basis: `docs/reports/2026-07-02-harness-audit.md` (22 findings, 22 fixed) PLUS the two post-review fixes (ci-orphan latency `86d02c7`, duplicate-ID `25257d1`) and the P2 fixes. Note that `dffa7db` (paul-apply-review-gate tip) is included. Do NOT merge directly / force-push. If this repo is a submodule of claude-harness, also bump the submodule pin in the parent per its usual flow.
4. **After PR up + CI green:** `git stash drop` the backup `stash@{0}` on `feat/paul-apply-review-gate` (content preserved in commit `6ada6b7`).

## Pre-existing issues noted (NOT introduced this session — flag to user, don't silently fix)
- **Two stale `status: in-progress` plans** will fail-closed the next coding-team pipeline / `/release`: `docs/plans/2026-06-14-coding-team-fastlane.md` and `docs/plans/2026-06-20-coding-team-workflow-refactor-design.md`. Resolve (mark `status: complete`) before running `/release`, or open the PR manually with `gh` (avoids the lifecycle gate). Ask the user which plans are actually done.
- `docs/handoff/2026-06-20-workflow-api-spike-RESUME.md` carries a "STATUS UNCONFIRMED / D199 pending" banner — deliberately unresolved; ask the user, don't invent a resolution.

## Known-acceptable facts (from the original handoff — not bugs)
- `test_prompt_dispatcher.py` excluded in CI (`.github/workflows/ci.yml`) — depends on `~/src/engram/.base/hooks` (absent on runners); passes locally.
- `E501` ignored in `pyproject.toml` (pre-existing cosmetic; F/E4xx/E7xx active).
- `cookbook/context-inheritance-matrix.md` still names deleted agents — deliberate historical artifact, allowlisted in `scripts/check-indexes.py`.
