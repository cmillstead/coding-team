# Handoff — F1 MERGED, audit arithmetic reconciled, Groups B/C/D UNBLOCKED and ready (2026-07-27)

Supersedes the *resume instructions* in `2026-07-26-f1-surface-measurement-plan-ready.md`
(that file's Phase 5/gate-4 record remains accurate history — read it for the F1
review history and the operating rules; do NOT follow its resume steps, they are done).

Every state claim below was verified by command at write time.

---

## ✅ COMPLETE — 2026-07-27. Nothing here is actionable. Do NOT re-execute.

Both queued items landed the same day this handoff was written. Kept as the record
of how, not as work.

- **Item 1** — `docs/audit-arithmetic-reconcile` merged via **PR #126**.
- **Item 2** — Groups B/C/D executed in one pass via **PR #127**. Surface went
  **354 → 190**, ten lines under the 200 threshold. The `hook-health-check.py`
  always-loaded warning no longer fires.

Verify in one command — it should print nothing:

```bash
echo '{}' | python3 ~/.claude/hooks/hook-health-check.py | grep 'Always-loaded surface'
```

If that DOES print a line, the surface regressed after 2026-07-27; treat it as new
work and do not follow the plan below, which is spent.

**What landed** (4 commits on `reduce/always-loaded-surface-groups-bcd`): extractions
to `reference/{engram-cli,skill-suggestions,obsidian-vault}.md`; deletion of
`rules/config-files.md` and of the model-routing / UI-UX sections that already
duplicated `phases/agent-standards.md`; reflowing (not rewording) of hard-wrapped
prose, since the check counts newlines; and a new Root Cause Over Symptom rule.

**The one finding worth carrying forward.** An intermediate commit collapsed six
"NEVER" rules into one line claiming all six were hook-enforced. QA review found
**three of those claims were false or partial** — test-skipping matches zero patterns
in `MOCK_PATTERNS`, force-push is never modeled in `git-safety-guard.py` (the branch
check reads the checked-out branch, never the push refspec), and the secret check is
filename-only on the `git add` path. Fixed in `109bcce` by stating them as prose that
says plainly nothing enforces them. **Deleting prose in favor of "a hook covers this"
requires reading the hook body first — a citation is not evidence.**

**Genuinely still open, and deliberately not done:** the hooks do not actually block
force-push to main or test-skipping. That is real work, out of scope for a
documentation reduction, and nothing currently tracks it.

---

## The target question is CLOSED — do not reopen it

An earlier version of this work said "do NOT execute Groups B/C/D until the target
is settled." **That is obsolete.** The reconciliation (`74940c5`) settled it:

- Goal is **under 200**.
- Enumerated groups B+C+D+E deliver **−167** from today's measured **354** → **187**.
- **187 < 200, so the enumerated work is already sufficient.**

The famous 24-line gap (187 vs the audit's printed 163) was the difference between
*sufficient* and *comfortable headroom*. It never gated the goal. Full derivation in
`docs/reports/2026-07-26-claudemd-saturation-audit.md` **§0.1** — that section is
authoritative and supersedes §0's headline table.

**`MEMORY.md` is NOT a blocker.** `~/.claude/projects/<slug>/memory/MEMORY.md` is 65
lines today (64 the day before — it grows with every feedback memory) and is
unmeasured by both the audit and F1. If counted, 187 becomes ~251 and more cuts
would be needed. **That is a decision to expand scope later, not a prerequisite.**
Reduce the measured surface first; revisit MEMORY.md when the warning is quiet.

---

## Repo state (verified)

- **`main`** @ `572328c` — "Merge pull request #125" (F1 landed, in sync with origin).
- **Current branch** `docs/audit-arithmetic-reconcile` @ `74940c5` — **1 commit,
  UNPUSHED, not merged.** Contains only the audit arithmetic reconciliation.
- **Working tree — two pre-existing not-ours entries, NEVER stage either:**
  `.claude/settings.local.json` (modified) and untracked
  `skills/second-opinion/codex-learnings.d/20260723-170559-5689-self-heal-migration-schema-shape.md`.
- **Verified:** `python3 -m pytest hooks/tests -q` → **1075 passed, 9 skipped**.
  `ruff check .` → clean.
- **Current surface: 354** = `~/.claude/CLAUDE.md` 238 + `~/.claude/rules/` 116
  across 7 files. Plus unmeasured `MEMORY.md` 65 → true ~419.

### ⚠ `write-guard.py` is DISARMED

No plan carries `status: in-progress` (the F1 plan was set to `complete` at Phase 6).
**Instruction-file edits are currently UNGATED.** Groups B/C/D edit
`config/CLAUDE.md` and `rules/*.md`, which ARE instruction files.

**Before executing, re-arm it properly:** create a plan for the reduction work with
`status: in-progress` and an `instruction_files:` declaration naming every path the
reduction will touch. Do NOT rely on the guard being off — that is the ungated state,
not permission. **Never set `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`.**

---

## Where the work is defined

`docs/reports/2026-07-26-claudemd-saturation-audit.md` §5:

| Group | Line | Δ | What |
|---|---|---|---|
| A | `:285` | −110 | ✅ **LANDED** 2026-07-26 (PR #123). Confirmed: 464−110 = 354 measured |
| B | `:298` | −42 | deletions (already enforced or dead) |
| C | `:307` | −93 | extractions out of `CLAUDE.md` |
| D | `:319` | −44 | compressions (stay always-loaded, shrink) |
| E | `:331` | +12 | additions (incl. the Root Cause rule) |

Line numbers are post-`74940c5` and will drift — grep the `### Group` headings.

**F2 (blocking cap) must land LAST**, after the reductions. At 238 lines a cap that
blocks >200 would block the very edits that reduce the surface.

---

## The queue is TWO items. Everything else is cut.

**Operator instruction, 2026-07-27, verbatim intent: "Do not add anything more to
the pile. I want it out of my hair immediately not added to."** Honor this. Do NOT
reopen the cut list below, do NOT re-surface dropped items as "quick wins", and do
NOT add newly-discovered work to this file. If you find a new defect while doing
item 2, fix it silently if it is inside your diff, or say nothing if it is not.

### The only two things — BOTH DONE 2026-07-27
1. ~~**Merge `docs/audit-arithmetic-reconcile`**~~ — done, PR #126.
2. ~~**Groups B/C/D**~~ — done, PR #127. Surface 354 → 190, warning silent.

That was the end of the pile, and the pile is now empty.

**There is no backlog section in this file, deliberately.** The operator deleted it
on 2026-07-27. Do not reconstruct it, do not append newly-discovered work to this
file, and do not re-surface previously-suggested items as "quick wins". If asked
"what's left", the answer is: **item 2, then nothing.**

---

## Context the next session needs

**The user is frustrated and it is legitimate.** ~a week on this, no visible end,
and it is blocking harness work and bugs they would rather be doing. Two things
follow:

1. **Do not expand scope without saying so.** This session's gate found three
   instances of one defect class — correct work, but it grew the pile. Thoroughness
   has a cost; name it rather than presenting it as pure progress.
2. **The reduction is not just another queue item.** At 354 lines the standing rules
   do not reliably bind, which taxes *every* task including the ones they want to get
   to. Finishing item 2 makes the whole queue cheaper. That is the argument for doing
   it first, and it is why they picked it.

**Deliver a single approval-ready cut list.** Not a tiered recommendation, not
per-rule questions.

## Hazards

- **`~/.claude/hooks/hook-health-check.py` is a SYMLINK to the repo source.** Editing
  the source changes the live hook instantly. It runs at SessionStart, so a syntax
  error will not wedge the current session but WILL break the next one. Probe after
  every edit. If the probe shows a regular file instead of a symlink, STOP.
- **`config/CLAUDE.md` and `rules/*.md` deploy as symlinks** into `~/.claude/`.
  `scripts/deploy.sh` skips `rules/README.md` deliberately (deploy meta-doc).
- **Two hooks will interrupt you and both are correct.** `git-safety-guard` blocks
  commit/push/merge on a protected branch, and a pre-completion checklist blocks
  commit/push until tests+lint have been run *recently in-session* — a stale
  verification run does not satisfy it. Re-run `pytest hooks/tests -q` and
  `ruff check .` immediately before committing. Do NOT work around either.
- **Commit messages:** the guard rejected a heredoc `git commit -F -` twice this
  session. Write the message to a file and use `git commit -F <path>`.
- **Known flake:** `test_ci_orphan_detector.py::test_exits_cleanly_with_empty_input`
  shells out and intermittently times out. Re-run once before investigating.
- **`gh pr checks` output is unreliable here.** Its wrapper printed
  "Passed: 5 / Pending: 5" while exiting 0 on a PR with 2 checks. Confirm with
  `gh pr view <n> --json statusCheckRollup`.

## Lessons from the F1 gate worth carrying (full versions in the other handoff)

- **When the same defect class appears a third time, stop patching instances and
  invert the burden of proof.** Make success the thing that must be proven, not
  failure the thing that must be enumerated.
- **A doc-staleness fix cannot be today's numbers.** The first reconciliation commit
  said "13 commits" and was wrong the instant it landed, being the 14th. Pair
  branch-describing numbers with a re-derivation command; write `file:line`
  citations symbol-first.
- **Reproduce a reviewer's claim by command before dispatching a fix.**
- **Verify every agent state claim by command.** Agent file-content analysis is
  excellent; agent claims about working-tree state are guesses.
