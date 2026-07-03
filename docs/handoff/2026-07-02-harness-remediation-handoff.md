# Handoff: Finish the 2026-07-02 Harness Remediation

This is an in-repo handoff. If you are Claude Code in this repo: execute the tasks below.

## Context

A full harness audit (22 findings) was run and remediated in a Cowork session on 2026-07-02. The full report is at `docs/reports/2026-07-02-harness-audit.md` in this repo. All remediation decisions are final — do NOT relitigate them; your job is verification and shipping only.

## Current state (already done — do not redo)

- Repo is on branch `fix/harness-audit-2026-07-02` at commit `e76ef75`, working tree clean. Based on `feat/paul-apply-review-gate` HEAD (`dffa7db`); the first branch commit (`6ada6b7`) snapshots the previously-uncommitted working tree, so nothing was lost.
- A backup stash exists (`stash@{0}` on `feat/paul-apply-review-gate`) — redundant with commit `6ada6b7`, kept until final verification.
- The 6 dead agent symlinks (`~/.claude/agents/ct-{builder,reviewer,qa,harden-reviewer,plan-reviewer,prompt-reviewer}.md`) were already removed.
- `scripts/deploy.sh` was already re-run: reports "All hooks registered." (the verifier was also fixed in `e76ef75` to check the pretooluse/posttooluse dispatchers).
- `~/.claude/rules-on-demand/failure-taxonomy.md:54` dead pointer already fixed.
- Already verified passing: `python3 scripts/check-indexes.py` (exit 0) and `python3 -m ruff check .` (0 errors) on this exact tree.

## Your tasks

1. **Run the hook test suite** (the one verification not yet confirmed on this machine):
   ```bash
   cd hooks && python3 -m pytest tests/ -k "not llm_eval and not llm_judge" -q
   ```
   Expected: everything passes (in a sandbox verification of this tree: 872+ passed, 2 skipped, 0 failed, with `test_prompt_dispatcher.py` excluded). On THIS machine `test_prompt_dispatcher.py` should also pass since `~/src/engram` exists here — include it. If any test fails, diagnose before shipping; do not skip or disable tests. Known-acceptable skips: 2 conditional skips in `test_agent_smoke.py` ("Not a read-only auditor").
2. **Sanity-check the deployed harness**: `bash scripts/deploy.sh` should end with "All hooks registered." and `python3 scripts/check-indexes.py` with "all checks passed".
3. **Open a PR** from `fix/harness-audit-2026-07-02` (target: the repo's default base branch; note the repo may be a submodule of claude-harness — if so, also bump the submodule pin in the parent repo per its usual flow). Use the audit report `docs/reports/2026-07-02-harness-audit.md` as the PR description basis: 22 findings found, 22 fixed. Do NOT merge to main directly and do NOT force-push.
4. **After PR is up and CI is green**: `git stash drop` the backup stash on `feat/paul-apply-review-gate` (its content is preserved in commit `6ada6b7`).

## Known-acceptable facts (not bugs — do not "fix")

- `test_prompt_dispatcher.py` is excluded in CI (`.github/workflows/ci.yml`) with an inline comment: it depends on `~/src/engram/.base/hooks` which doesn't exist on runners. Locally it should pass.
- `E501` is ignored in `pyproject.toml` (106 pre-existing cosmetic violations; F/E4xx/E7xx active).
- `cookbook/context-inheritance-matrix.md` still names deleted agents — deliberate historical artifact, allowlisted in `scripts/check-indexes.py`.
- `docs/handoff/2026-06-20-workflow-api-spike-RESUME.md` carries a "STATUS UNCONFIRMED / D199 pending" banner — deliberately unresolved; ask the user, don't invent a resolution.

## Commit log of the branch (for the PR description)

- `e76ef75` fix: deploy.sh registration verifier checks pretooluse/posttooluse dispatchers
- `edb3da1` fix: ignore pre-existing E501; generalize stale prompts refs in prompt-craft
- `a2ebde8` docs: add 2026-07-02 harness audit report
- `d513d33` refactor: command stubs, agent boilerplate factoring, agents/reference/, check-indexes verifier (F7,F14,F17,F19,F20,R2)
- `2671703` docs: regenerate indexes, refresh memory to July 2026, wiki-generation extraction, plans INDEX (F5,F8,F10,F12,F15,F21,F22)
- `bcb40c3` refactor: resolve stale cookbook fork, delete 6 dead agents, fix Teammate anti-pattern, README rewrite (F1,F2,F6,F9,F14,F18)
- `2d74b19` fix: hook portability, loop-detection key bug, crash guards, lint config (F3,F4,F11,F16,R3)
- `6ada6b7` chore: snapshot uncommitted working tree (pre-remediation baseline)
