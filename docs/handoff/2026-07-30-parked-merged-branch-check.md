---
trigger: context-80
date: 2026-07-30
branch: harness/parked-merged-branch-check (submodule /Users/cevin/.claude/skills/coding-team)
---

# Handoff — Parked-Merged-Branch Session-Start Check

**Resume rule (per ~/.claude/CLAUDE.md): FIRST run `git fetch`, then
`gh pr list --state all --head harness/parked-merged-branch-check` — if a PR exists
and is MERGED, everything below is done; just verify and clean up. Do not trust this
document over the repo.**

## Task

Add parked-merged-branch detection to the SessionStart hook so every session reports
when the repo root or a submodule checkout sits on a branch whose merged PR's
`headRefOid` equals local HEAD, with an absolute-path recovery command. Motivated by
the user repeatedly having to ask "is everything merged / why aren't we on main."

Plan (Codex-gated, 2 rounds, 18 findings applied): `docs/plans/2026-07-30-parked-merged-branch-check.md`
(status: in-progress — flip to `complete` at Phase 6 end). Tier: Medium.
`instruction_files: hooks/ci-orphan-detector.sh, hooks/tests/test_ci_orphan_detector.py`.

## State at handoff

- **Uncommitted working-tree changes** on the branch (nothing committed yet):
  - `hooks/ci-orphan-detector.sh` — new detection section + 3-way output refactor
  - `hooks/tests/test_ci_orphan_detector.py` — 29 tests (5 existing + 24 new)
  - `README.md` — line 457 one-line description update (doc-drift MUST_FIX; note:
    an implementer once stashed this as "unexplained drift" — it is legitimate,
    orchestrator-authored)
- **Gates complete:** plan Codex gate ✓ (2 rounds) · implementation ✓ (TDD, RED
  proven) · full suite ✓ 1142/0/9 independently verified · live smoke ✓ · QA
  reviewer ✓ (7 findings, ALL fixed in a second implementer round) · doc-drift ✓
  (1 MUST_FIX fixed in README) · post-exec Codex diff review ✓ RUN — returned ONE
  P2.
- **IN FLIGHT:** implementer agent `ab178e6dde5704ab9` (resumable via SendMessage)
  fixing the last P2: shell-quote `${repo}` (×2) and `${base}` in the printed
  recovery command (hooks/ci-orphan-detector.sh:130) + update the test
  expected-builder to the quoted form. After it reports: re-run targeted +
  full suite independently, then proceed to ship.

## Remaining (in order)

1. Verify P2 fix: `python3 -m pytest hooks/tests/test_ci_orphan_detector.py -q`
   then full `hooks/tests` (expect ~1142+ passed / 0 failed), `bash -n` the hook.
2. Quick Codex confirmation of the quoted command (finding-resolution check, not a
   new round).
3. Commit on the branch (style `feat:`), push, PR to coding-team main, merge
   (submodule PRs merge with a MERGE COMMIT per memory), verify with
   `gh pr view --json state,mergeCommit`.
4. Flip plan frontmatter `status: in-progress` → `complete` (de-arms write-guard).
5. Return BOTH checkouts to main + ff (the new hook will nag about exactly this
   from now on).
6. Outer repo (~/.claude): gitlink bump branch + PR (never direct to main) — this
   also clears the pre-existing cosmetic drift (outer main records `c8fb5e3`,
   submodule main tip is `744d8a5`).
7. Completion report must mention: QA's pre-existing observation that legacy
   sections hardcode `timeout 10` with no gtimeout fallback (out of scope — user
   decides); stopped stale agents `save-dup-fix` + `arming-planner` earlier.

## Acceptance criteria

- Session start in ~/.claude with both repos parked on merged branches prints the
  warning with PR numbers and absolute-path recovery commands; on main → silent.
- Hook NEVER exits nonzero / never emits anything but ONE {"decision":"allow",...}
  JSON object; ≤2 gh lookups per run, each `timeout -k 1 2`-wrapped; no timeout
  binary → lookups skipped entirely.
- Legacy orphan/stale output byte-identical when no parked repos (pinned by tests).

## Session decisions of record

- Phase 1 approval = user's "lets fix this problem"; Phases 2/3 collapsed into the
  plan's Design section (stamped DECISION in-conversation).
- Codex rounds capped at 2 per the new rule; round-2 findings applied without a
  third dispatch; diff review was the independent re-check.
- Telemetry logged via `harness codex --log` (plan review, 18 findings).
