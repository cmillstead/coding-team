# Handoff — Codex-gate lockdown: no skippable path for plan/diff cross-model review (TRK-184)

## Run this from a coding-team-rooted session
Start the session in `~/.claude/skills/coding-team` (NOT `~/.claude`). Invoke:
`/coding-team docs/handoff/2026-08-26-codex-gate-lockdown.md`
This is instruction-file + hook work — it goes through the full pipeline (design → plan → execute), with every touched instruction file declared under the plan's `instruction_files:` frontmatter (inline comma list, submodule-relative — a YAML block list fails closed).

## Task
The user's directive (2026-08-26, verbatim intent): **every single plan and every single diff must be Codex-reviewed; there must be no possible way for the model to skip it.** Rules alone are rejected by the user ("rules don't work"). The chosen design is **Option 1: hooks + CI backstop** — user picked it explicitly.

Three escape hatches exist today; close all three:
1. **Tier matrix legally allows skips** — `phases/task-weight.md:48` (plan review SKIPs at Trivial/Small) and `:52` (post-exec review SKIPs at Trivial), restated in the reading rule at `:60` and in `SKILL.md:121` (Phase 4 exit gate) and `SKILL.md:129` (Phase 5 exit gate 4). Down-tiering is the model's main skip route.
2. **Honor-system checkbox** — `hooks/coding-team-lifecycle.py` gates on a plan-file checkbox the model itself writes: `- [x] Second-opinion review` passes (line 64), a `skip: <reason>` suffix passes (lines 66–67), a missing checklist section passes via back-compat allow (lines 57–58, 21). No evidence Codex ever ran.
3. **Unguarded exits** — nothing checks `git push` / `gh pr create` for a completed diff review. Telemetry exists (`~/.claude/harness-codex.jsonl`, written by the model via `harness codex --log` per `skills/second-opinion/SKILL.md:191`) but nothing reads it, and it's model-authored anyway.

## Design (approved by user — Option 1)

### Layer A — rulebook: all tiers run both reviews
- `phases/task-weight.md`: matrix rows 48 + 52 become RUN (required) at ALL FOUR tiers; fix the reading rule (line 60) and the recompute prose (~lines 87–95, "Trivial diffs still skip" must go).
- `SKILL.md:121` and `:129`: remove the Trivial/Small skip clauses.
- `phases/post-execution-review.md:42,61,65` and `phases/completion.md:5`: remove the `skip: <reason>` user-override route (the checkbox itself is being replaced — see Layer B). Grep the repo for remaining `skip:`-checkbox mentions (`grep -rn "skip:" phases/ SKILL.md`) and sweep all of them.
- Codex `challenge` (task-weight.md:58,70–72) is OUT OF SCOPE — unchanged. Only `review` (plan + diff) is being locked.

### Layer B — receipts instead of checkboxes (hook enforcement)
**Receipt writer (new, small):** a wrapper script in this repo (suggest `skills/second-opinion/scripts/codex-receipt.py`, deployed however Phase-2 design decides — note deploy.sh symlinks hooks/agents/reference, not skill scripts; scripts are invoked by absolute path, so no deploy change may be needed). The second-opinion skill's codex invocation runs THROUGH it. It:
- runs the codex command it's given, captures the verdict,
- appends a receipt line to `~/.claude/codex-receipts.jsonl` (NEW file — do NOT extend `harness-codex.jsonl`; `~/.claude/bin/harness` lives in the PARENT repo and its `--log` validator can't be touched from this session) with: `mode` (`plan`|`diff`), `target` (plan path for plan mode; repo root for diff mode), `git_head` (SHA at review time), `diff_sha256` (for diff mode: hash of `git diff <merge-base origin/main>..HEAD` output; define the exact command in Phase 2 and pin it in tests), `verdict`, `ts`.
- The model never writes receipts by hand; only the wrapper does, and only after codex actually returns. (A determined forger could still run the script — the CI backstop in Layer C is the answer to that; locally this closes every *rationalized* skip.)

**`hooks/coding-team-lifecycle.py`:** replace checkbox reading with receipt reading. Gate passes only if `codex-receipts.jsonl` holds a `mode:"diff"` receipt whose `git_head`/`diff_sha256` matches the CURRENT state of the active plan's repo. Delete: the `skip:` escape (66–67) and the no-section back-compat allow (57–58). Keep the ambiguous-plan fail-closed behavior. The plan checkbox line can stay as human-readable status, but the hook must not trust it.

**`hooks/git-safety-guard.py`:** extend the existing PreToolUse commit/push checklist (docstring line 10; verification tracking around lines 379+): when the command is `git push` or `gh pr create` **in a repo with an active coding-team plan**, additionally require a fresh matching `mode:"diff"` receipt. Plan-side: when Phase 5 starts (first gated commit under an in-progress plan), require a `mode:"plan"` receipt whose `target` is the active plan path. Two hard constraints from TRK-176's corpse:
- reuse the recency-window prune pattern (commit `36c023b`) — do NOT add a new count-capped buffer; stacked conditions on this same door is exactly where the last eviction bug lived.
- scope the new requirement to repos with an active in-progress plan; do not break pushes in non-pipeline repos (e.g. the parent-repo pointer-bump flow in `docs/handoff/2026-08-24-claude-side-activation-and-pointer-bump.md` step 2 must still work with only a ruff pass).

### Layer C — CI backstop (the layer the model cannot reach)
- New job (or extend `.github/workflows/ci.yml`) in THIS repo: on `pull_request`, run the Codex review server-side against the PR diff; fail the check on a FAIL/REVISE verdict or if codex is unreachable (fail closed).
- Needs a Codex/OpenAI auth secret in GitHub → **USER-HELD STEP 1** (below).
- `main` currently has NO branch protection (verified 2026-08-26: `gh api repos/cmillstead/coding-team/branches/main/protection` → 404 "Branch not protected"). Without required-checks protection, a red check doesn't block merge → **USER-HELD STEP 2**.

## Acceptance criteria
- No tier or wording anywhere in `SKILL.md`/`phases/*.md` permits skipping plan or diff Codex `review`.
- `coding-team-lifecycle.py` and `git-safety-guard.py` gate on wrapper-written receipts; `skip:` and no-section allowances are gone; tests pin BOTH directions (receipt present → allow; absent/stale/hash-mismatch → block) per the mutation-test rule.
- CI job runs Codex review on PRs and fails closed.
- Full suite green locally and in CI; `python3 scripts/check-indexes.py` green (phase files are cross-indexed).

## Repo state (measured 2026-08-26)
- **coding-team**: on `main` = `b662415`, in sync with origin/main. Dirty: `M docs/project-evals.md` (one uncommitted retro line from TRK-176 — commit it as its own `docs:` commit early in this session, it's this repo's content) + 7 pre-existing untracked files (4 handoffs incl. this one, 2 retros, 1 codex-learnings entry) — leave the untracked ones.
- **No open PRs** (`gh -R cmillstead/coding-team pr list` → empty).
- **Parent** `~/.claude` pointer is at `b662415`, clean at pointer level — do not touch the parent repo from this session.
- Tracker: **TRK-184** (p1, coding-team) is this work.

## Remaining actions (cold-start, in order)

### 1. Commit the stray retro line
- **How:** `git -C /Users/cevin/.claude/skills/coding-team add docs/project-evals.md` then commit `docs: add TRK-176 retro eval item (sibling-classifier polarity check)` on the feature branch this pipeline creates (not main — direct-to-main commits are hook-blocked).
- **Looks-broken-but-isnt:** the pre-commit checklist wants a recent verification pass; run `python3 -m ruff check hooks` (from the repo root) right before the commit, same as the TRK-176-era flow.

### 2. Run the pipeline on this handoff
- **How:** `/coding-team docs/handoff/2026-08-26-codex-gate-lockdown.md` from the coding-team root. Weight: **Medium minimum** (instruction files + hooks = risk signals). Phase 2 must settle the open micro-decisions: exact diff-hash command, receipt freshness window, wrapper deploy path, CI codex invocation (the CLI needs `< /dev/null` and file-path args — `codex review` ignores stdin, see memory `reference_codex-exec-invocation`).
- **Looks-broken-but-isnt:** (a) the lifecycle hook will gate THIS pipeline too — the plan needs its own Second-opinion checkbox until the new mechanism ships (you are editing the gate you're standing on; sequence hook edits LAST and flip the plan to the new receipt mechanism only after the wrapper exists). (b) `hooks/tests/test_prompt_dispatcher.py` fails on any machine without the maintainer's engram checkout — CI excludes it; exclude it locally too. (c) LLM-eval tests are excluded via `-k "not llm_eval and not llm_judge"`.
- **Gate commands (ALL RUN GREEN 2026-08-26 from this baseline — `b662415`):**
  - `python3 -m pytest hooks/tests/ --ignore=hooks/tests/test_prompt_dispatcher.py -k "not llm_eval and not llm_judge" -q` → `1492 passed, 0 failed, 11 skipped` (takes ~8 min)
  - `python3 -m ruff check .` → `All checks passed!`
  - `python3 scripts/check-indexes.py` → `all checks passed`

### 3. USER-HELD STEP 1 — CI secret
- The user must add the Codex auth secret (e.g. `OPENAI_API_KEY`) to `cmillstead/coding-team` repo secrets before the CI job can pass. The pipeline should ship the workflow regardless; the job fails visibly until the secret lands.

### 4. USER-HELD STEP 2 — branch protection
- The user must enable branch protection on `main` requiring the new codex-review check (Settings → Branches, or `gh api -X PUT repos/cmillstead/coding-team/branches/main/protection ...`). Until then the CI check reports but cannot block merges.

### 5. Parent-side activation (SEPARATE ~/.claude-rooted session, after merge)
- Same pattern as `docs/handoff/2026-08-24-claude-side-activation-and-pointer-bump.md`: run `bash scripts/deploy.sh` (refreshes hook symlinks), bump the submodule pointer via branch+PR, decide whether `~/.claude/codex-receipts.jsonl` gets git-tracked in the parent (telemetry policy says tracked — `reference_harness-jsonl-tracking-policy`). Write that handoff at the end of the coding-team session.

## Blockers / paused
- None at start. Steps 3–4 are user-held and can land in parallel with the build.

## Decisions (canonical homes)
- **Option 1 (hooks + CI backstop) chosen by user 2026-08-26** → tracker TRK-184 + memory `project_codex-gate-lockdown.md` (both written).
- **All tiers run both reviews; no skip escape anywhere** → will live in `phases/task-weight.md` itself once shipped; until then TRK-184 + the memory file.
- **Receipts in a NEW `~/.claude/codex-receipts.jsonl`, wrapper-written, not via `harness codex --log`** (parent-repo CLI untouchable from this session) → this file + Phase 3 design doc when written.
- **Codex `challenge` untouched; only `review` locked** → this file; restate in the design doc.

## Related
- `docs/handoff/2026-08-23-trk-176-git-safety-guard-fix.md` — the recency-window pattern the new guard condition must reuse
- `skills/second-opinion/SKILL.md` (telemetry emit at line 191; 2-round cap at line 110 stays as-is)
- Memory: `reference_codex-exec-invocation`, `reference_git-safety-guard-architecture`, `reference_instruction-files-frontmatter-inline-only`
