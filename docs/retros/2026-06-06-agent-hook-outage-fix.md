# Retrospective: Agent-tool PreToolUse outage — fix, hardening, drift guard

**PRs:** #60 (fix), #62 (hardening, stacked on #60), #61 (deploy-drift guard)
**Branches:** fix/update-input-merge, fix/hooks-hardening, fix/deploy-drift-check
**Date:** 2026-06-06

## Context

A `/distill` run had all 6 parallel Agent dispatches rejected by the Agent-tool PreToolUse
hook. Root cause: `codesight-hooks.py:handle_pre_agent` called `update_input({"prompt": injected})`,
and `update_input` emitted its argument verbatim as `hookSpecificOutput.updatedInput`. Because
CC's `updatedInput` REPLACES the tool input (it does not merge), this stripped the Agent tool's
required `description` field, so every dispatch failed schema validation. A per-call strip that
hit all 6 calls identically — not a batch-specific bug.

## What went well

- **The audit caught a Critical the orchestrator missed.** The harness-engineer auditor found
  that the fix had been applied only to the DEPLOYED tree (`~/.claude/hooks/`) and NOT the
  canonical SOURCE (`skills/coding-team/hooks/`). The next `deploy.sh` would have `cp`'d stale
  source over the fix and re-introduced the outage. Without the audit, the "fix" would have
  silently reverted. This single catch justified the whole audit pass.
- **Cross-model challenge earned its cost.** Codex (second-opinion challenge) confirmed it could
  NOT break the real caller path or the empty-prompt guard — corroborating correctness — and
  found one in-scope issue Claude's own review missed: a regression test that passed on the OLD
  broken code (`test_partial_wins_on_key_collision`), giving false confidence. Fixed by replacing
  it with a direct merge-semantics unit test that fails on the old implementation.
- **Fixed the class, not just the instance.** Rather than only patching the helper, shipped a new
  `deploy-drift-check.py` SessionStart hook that detects source↔deployed drift — the exact failure
  mode that caused the near-miss. Verified live: it flags an artificially perturbed deployed file
  and goes silent once synced.
- **Worktree isolation kept the user's WIP safe.** The user's checkout (`fix/git-safety-guard-cwd`)
  had unrelated uncommitted WIP. Every clean branch was built via `git worktree` + cherry-pick off
  `main`, so the working tree was never switched or disturbed.
- **Claims were verified, not asserted.** The batch concern ("does it handle multi-call?") was
  answered empirically — 6 concurrent hook invocations with distinct descriptions + 4 live parallel
  Agent dispatches — not by reasoning alone.
- **Right-sized models.** haiku for the mechanical test swap; sonnet for the hook implementation and
  resilience work; opus for the harness-engineer audit.

## What to improve

- **The original bug was an orchestrator mistake: edited the deployed copy, not the source.**
  `~/.claude/hooks/` is a DEPLOYED artifact; the source of truth is `skills/coding-team/hooks/`,
  deployed via `scripts/deploy.sh`. The hotfix (and the first coding-team implementer, inheriting
  the framing) both edited the deployed tree. This is the documented deploy-drift class
  (memory/project-cycle14-audit-2026-03-26.md) recurring in the fix for an unrelated bug.
  **Lesson: for any hook change, edit `skills/coding-team/hooks/<file>` then run `deploy.sh`.
  Never hand-edit `~/.claude/hooks/`.** (Now also enforced by detection via deploy-drift-check.py.)
- **Implementer subagents auto-commit despite "do NOT commit" in the prompt.** This happened on
  every implementer dispatch this session (4×), producing commits on the wrong branch
  (`fix/git-safety-guard-cwd`) that the orchestrator then had to squash and cherry-pick onto clean
  branches. The instruction is silently ignored — the agent's built-in TDD-commit behavior wins.
  **Lesson: either give the implementer a genuine no-commit mode, or stop fighting it — plan for
  the commits and isolate them afterward. Don't write "do NOT commit" and expect compliance.**
- **Squash-merging a stacked PR forces a downstream rebase.** Merging #60 (squash) flipped #62
  to CONFLICTING, because #62's branch still carried #60's original commit, which clashed with
  main's new squash commit. Resolved with `git rebase --onto origin/main <old-base>` (the
  already-applied commit dropped, only the new commit replayed). **Lesson: when squash-merging
  stacked PRs, expect to rebase the downstream branch onto the updated main before it will merge —
  or merge the base PR with `--merge` to keep its commit in history.**
- **The commit guard requires a test run in the same shell call.** `git-safety-guard.py` blocks a
  `git commit` unless verification ran; the fix is to lead the same Bash call with `pytest`
  (truncation drops the tail, so the test must come first). Known pattern — internalize it to avoid
  a blocked-commit round trip.

## Recurring patterns

- **Deploy drift recurred inside the fix itself.** The strongest signal the drift guard was overdue:
  the very failure class the repo has documented for cycles showed up again, in a fix authored this
  session. Periodic-audit value re-confirmed; the new hook now surfaces it automatically.
- **"do NOT commit" to implementers is a dead instruction.** Four-for-four ignored. This is a
  prompt-vs-built-in-behavior conflict, not a wording problem.
- **Verify the deployed artifact, not just the source.** Tests run against source
  (`conftest.HOOKS_DIR` → source tree); the live hook is the deployed copy. Both must be checked,
  and `deploy.sh` must run between source edit and "done."

## Metrics

- **PRs merged:** 3 (#60, #62, #61) into `main` (6ea1d74, 99ca1d1, cea4c9c), in dependency order.
- **Implementers dispatched:** ~5 (fix, source-mirror, test-strengthen [haiku], drift-guard, resilience-hardening).
- **Audit:** harness-engineer (opus) + harden auditor (sonnet) + codex challenge (cross-model).
- **Tests:** 516 full hook suite green; +5 new (2 merge/field-preservation, 3 resilience fail-open).
- **Rework driven by audit/review:** 1 Critical (deploy drift), 1 in-scope test fix (codex P2),
  3 resilience follow-ups — all caught before merge.
- **Net new guard:** `deploy-drift-check.py` SessionStart hook (registered in settings.json).

## Action items

- [ ] Implementer agent (`agents/ct-implementer.md`): add a real no-commit mode, or remove "do NOT
      commit" from dispatch prompts and standardize orchestrator-side commit isolation.
- [ ] Document the stacked-PR merge guidance (rebase downstream after squash, or `--merge` the base)
      in the release/completion phase notes.
- [ ] Monitor deploy-drift-check.py for false positives from legitimate WIP-in-source (it will flag
      source files with uncommitted changes that haven't been deployed — accurate, but potentially
      noisy during active hook development).
- [ ] Consider promoting the headline lesson ("edit source not deployed for hooks") into
      `memory/consolidated-feedback.md` so it loads every coding-team session.
