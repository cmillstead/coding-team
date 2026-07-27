# Handoff — F1 surface-measurement: plan GATED & APPROVED, Phase 5 next (2026-07-26)

Supersedes nothing. Companion to `2026-07-26-saturation-remediation-phase1-complete.md`,
which is still accurate for everything outside this plan. Every state claim below
was verified by command at write time.

---

## ► RESUME HERE — Phase 5 execution

**The Codex plan gate is DONE. Verdict APPROVED after 5 rounds. Do NOT re-run it.**
Phase 4 and the gate are both closed. The next action is Phase 5:

1. Flip `docs/plans/2026-07-26-always-loaded-surface-measurement.md` frontmatter to
   `status: in-progress`. **This arms `write-guard.py` against the two paths declared
   in `instruction_files:`** — `hooks/hook-health-check.py` and
   `hooks/tests/test_hook_health_check.py`. Both reviewers confirmed that declaration
   is complete AND minimal; `docs/*` and `rules/*` are not gated
   (`hooks/write-guard.py:143-150` — verified).
2. Dispatch Tasks 1 → 2 → 3 → 4 **in that order, via `/coding-team`**. Do not reorder.
   Task 1 deliberately leaves an unwired function — a dark feature until Task 2 lands.
   **Do not report the feature complete after Task 1.**
3. Then the 4 blocking Phase 5 exit gates: full-suite test+lint, `ct-qa-reviewer`,
   doc-drift scan, post-exec Codex `review` (mode `review`, not `plan`). All RUN at Medium.

**State at handoff:** no code has changed; nothing is half-applied. The only working-tree
delta that is OURS is this handoff file (modified, uncommitted). `.claude/settings.local.json`
and the untracked `skills/second-opinion/codex-learnings.d/20260723-...` entry are
pre-existing and **must never be staged**.

**Baseline re-verified this session:** `python3 -m pytest hooks/tests -q` →
**1055 passed, 9 skipped**, exit 0. `ruff check .` → clean. Task 1 Step 0 still
re-measures `BASELINE` itself; later totals are `BASELINE + 10` / `BASELINE + 11`.
**Do not substitute absolute numbers** — the whole point of the `BASELINE + N` form
is that it survives a different tree.

---

## Repo state

- **Branch:** `feat/always-loaded-surface-measurement`, cut from synced `main` @ `0998201`. **One commit on it** — `60f4e40`, this handoff. (The previous version of this line said "zero"; it was written before the handoff was itself committed.) No code commits.
- **`main`** @ `0998201`. Merged today: #118–#124.
- **No plan is `status: in-progress`** — `write-guard.py` is DORMANT. If a future
  session finds instruction edits blocked, hunt for a stale `in-progress` plan
  before reaching for `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`. Never set it.
- **Working tree carries two pre-existing not-ours files** — `.claude/settings.local.json`
  (modified) and untracked `skills/second-opinion/codex-learnings.d/20260723-...-self-heal-migration-schema-shape.md`.
  **Never stage either.** The second is a live C27 learning entry AND the cause of
  the digest test failure (see "Known failures").
- **Verified baseline:** `python3 -m pytest hooks/tests -q` → **1055 passed, 9 skipped**.
  `ruff check .` → clean. I ran this myself; it is not carried from a brief.

## The plan

`docs/plans/2026-07-26-always-loaded-surface-measurement.md` — **1028 lines,
`status: planned`, gitignored** (`.gitignore:2`, so it will never be committed).

```yaml
instruction_files: hooks/hook-health-check.py, hooks/tests/test_hook_health_check.py
```

Both reviewers independently confirmed this declaration is complete AND minimal.
`docs/*` is not gated; `scripts/deploy.sh` is executed, not edited.

**Task order — 4 tasks, do not reorder:**

| # | Task | Model |
|---|---|---|
| 1 | `check_always_loaded_surface()` + `_count_lines()` + **10** tests, **12**-row mutation table | sonnet |
| 2 | Wire into `main()`, extend integration allowlist, live probe, `deploy.sh` | sonnet |
| 3 | Correct F3's prescription + 2 Appendix B prediction rows in the audit report | sonnet |
| 4 | Update the handoff's stale F1 entry and symlink counts | haiku |

**Task 1 Step 0 captures `BASELINE` first.** Later totals are `BASELINE + 10` and
`BASELINE + 11`. Do not reintroduce absolute numbers — the implementer may run
against a different tree, which is the whole point of the `BASELINE + N` form.

## What the fix is, and why this shape

`hooks/hook-health-check.py:186-190` globs `agents/*.md`, `phases/*.md`,
`skills/*/SKILL.md` against `repo_root = Path(__file__).parent.parent` (`:184`),
per-file threshold 200 at `:196`. All repo-rooted, so `config/CLAUDE.md` (238) and
`rules/*.md` are never measured.

The fix adds an **aggregate** check of the **deployed** surface —
`~/.claude/CLAUDE.md` + `~/.claude/rules/*.md`, summed. Reading the deployed
directory is the whole point: `~/.claude/rules/` is written by two repos
(2 symlinks from here, 5 regular files owned by the parent `claude-harness`), so
the deployed tree spans both owners by construction and the ownership question
does not need resolving for the measurement to be right.

**The audit's own F1 prescription was rejected in the plan** — adding `config/*.md`
+ `rules/*.md` to the existing glob list would measure 61 lines instead of 354, a
falsely reassuring number, and a per-file threshold never fires on 5-29-line rules.

Current surface: **354** = `~/.claude/CLAUDE.md` 238 + `~/.claude/rules/` 116.

**This is a WARNING, never a block.** It fires immediately at 354 and that is
intended. A blocking cap is audit finding **F2, which must land LAST**, after the
reductions — at 238 lines a cap that blocks >200 would block the very edits that
reduce it. The plan carries a dedicated "this is NOT F2" comparison table.

## Resume from here

1. ~~Finish the Codex plan gate~~ — **DONE 2026-07-26. Verdict APPROVED after 5 rounds.**
   The corrected pre-flight is below. **The audit line in the previous version of
   this handoff was wrong in two ways** — it dropped **P34** entirely (its file,
   `20260624-062659-dac1-cfgtest-as-production-path.md`, has no P/C prefix in the
   filename; the H1 is `# P34`) and its arithmetic did not reconcile (`24 + 7 = 31`,
   not the claimed 32). It also dismissed **C12** as `no-signal` when that battery
   actually fires 25× on the substring `lock` inside "block"/"deadlock" — an
   over-match, which per `_header.md` makes the entry *applicable* with a cheap ✓,
   never dismissible. Corrected:

```
mode: plan
signals: metric-aggregate(20), command-grammar(14), concurrency-lock(25, over-match)
dismissed(6): C2,C3,C5,C23,C24 N/A(scope-mismatch:diff vs mode:plan)
              C17 N/A(no-signal:path-equality, evidence: grep -cE
                  "ends_with|starts_with|strip_suffix|strip_prefix|same_file|is_same" = 0)
applicable(26): P1,P2,P3,P4 (floor) · P30,P31,P32,P33,P34 · C4,C10,C11,C12,C13,
                C14,C15,C16,C18,C19,C20,C21,C22,C25,C26,C27,C28
total: 26 + 6 = 32   floor-note: C28 floored — its category `dual-resolution-policy`
                     is NOT in `_header.md`'s 19-value enum, so it reads as untagged
```

2. **Phase 5 is the next action** — flip the plan to `status: in-progress` (this arms
   the write-guard against the two declared paths), dispatch Tasks 1-4 in order.
3. **Then the 4 blocking Phase 5 exit gates:** full-suite test+lint, `ct-qa-reviewer`,
   doc-drift scan, post-exec Codex `review`. All RUN at Medium.

## Hazards — read before touching anything

- **`~/.claude/hooks/hook-health-check.py` is a SYMLINK to the repo source.** Editing
  the source changes the live hook instantly. It runs at SessionStart, so a syntax
  error will not wedge the current session but WILL break the next one. Every task
  editing it must end with a live-hook probe; if the probe shows a regular copy
  instead of a symlink, STOP — do not hand-edit `~/.claude/hooks/`.
- **Known flake, not a regression:** `test_ci_orphan_detector.py::test_exits_cleanly_with_empty_input`
  shells out via `subprocess.run` and intermittently times out. Observed failing
  once and passing on immediate re-run this session. Re-run once before investigating.
- **Do not "helpfully" add `.resolve()`** while inside `hook-health-check.py` — see
  the discovery below. It is out of scope and would change the existing check's
  behavior mid-plan.

## Discovery this session — NOT in scope, deserves its own phase

**`Path(__file__)` is not symlink-resolved, so `repo_root` differs between the
deployed hook and the test suite.**

- Deployed (SessionStart banner): `agents/ct-implementer.md` 206, `skills/firecrawl/SKILL.md` 253, `skills/review/SKILL.md` 1467 — the last two do not exist in this repo.
- Under pytest: `phases/execution.md` 218, `agents/ct-implementer.md` 206, `phases/planning.md` 202.

Because `~/.claude/hooks/hook-health-check.py` is a symlink, `repo_root` evaluates
to `~/.claude` in production and to the coding-team repo under test. The existing
per-file instruction-length check has therefore been reporting on deployed
`~/.claude/agents/` and `~/.claude/skills/` all along, not on the repo its globs
were written for. Same root cause as F1 wearing a different hat.

It does not affect this plan — the new check reads `Path.home() / ".claude"`
explicitly and never touches `__file__`. Recorded in the plan's NOT-in-scope.

**This is also load-bearing for a plan gate:** it is *why* Task 2 Step 3's
early-return change cannot be tested. `check_instruction_file_lengths()` is
repo-rooted and unconditionally non-empty (3 files >200), so `main()` never
reaches the early return under test. The plan documents that as an **honest
coverage gap, verified by inspection only** — Failure Modes row at `:966`. Do not
"fix" it by stubbing; that breaches the no-mocks invariant, and the elaborate
real-file alternative was considered and rejected on GP#17.

## Codex plan gate — 5 rounds, APPROVED (2026-07-26)

19 findings across rounds 1-4; round 5 returned APPROVED with none. Verification gate
(`pytest hooks/tests` + `ruff check .`) run green before every re-dispatch; **every round
used a FRESH Codex session, never `exec resume`** — see lesson 5 below.

- **R1 (5):** one propagating factual error — the plan's rationale said
  `check_instruction_file_lengths` is repo-rooted and would measure 37 lines, but
  `Path(__file__)` is not symlink-resolved so the deployed root is `~/.claude`. Plus three
  real test-strength gaps (unbound counts, no threshold/boundary test, no non-`.md` decoy).
- **R2 (4):** **round 1's own fix had introduced a NEW wrong number** — I wrote that the
  pytest glob measures 37 when it measures 61 (`rules/*.md` includes `README.md` 24; 37 is
  the deployed *share*, a different quantity).
- **R3 (5):** four mutation-accounting prose errors, incl. mutation 6 undercounting (it
  fails all ten tests — the two zero-total tests fall through an inverted threshold).
- **R4 (10, one P1):** the per-assertion coverage claim was false — pytest aborts at the
  first failing assert, so seven assertions sit behind others and are never exercised.
  Notably it also reported **"Rows overcounting: 0"** — every row's named test does go RED.
- **R5:** APPROVED. Independently re-derived 238 + 116/7 files = 354, confirmed none of the
  three new symbols exist yet, confirmed no mocks in either test file.

**The design was never challenged in any round.** The function, the `main()` wiring, the
HOME-swap mechanism, and the deployed-path reading survived all five. Every finding after
R1's first item was about the plan's own SELF-DESCRIPTION — the mutation table and coverage
claims — not about what the code will do.

**R4's fix was structural, not another pass at the matrix.** Three attempts (R2/R3/R4) at
stating an exact 12×10 mutation→failure mapping each fixed the named cells and misstated
others. The fix was to scope the claim to what is verified — "apply mutation N, the NAMED
test goes RED" — and to declare explicitly that the table does not enumerate collateral
failures and that coverage is per-TEST, not per-assertion. **Do not "improve" the table by
re-attempting the exhaustive mapping; that is the loop this took five rounds to exit.**

## Review history — 20 findings, all closed (same-model rounds, pre-gate)

- **Round 1** (12: 2 P1, 2 P2, 8 P3). Headline: a Failure Modes row claiming
  `Tested? Yes` for a regression no test could observe — all seven aggregate tests
  pass `claude_dir=` explicitly and are blind to the default.
- **Round 2** (8: 1 P1, 7 P3), by a FRESH reviewer that traced every branch of
  `main()`. Headline P1: the mutation table added to fix round 1 contained a row
  that could not fire — **the same defect class recurring inside its own fix.**
- All 20 addressed with no false-positive claims. Both P1s were confirmed by me
  independently, by command, before routing them back.

## Still open from the prior handoff (unchanged, none started)

1. Two-repo ownership of `~/.claude/rules/` — measurement is what this plan fixes;
   the ownership swap (2 coding-team-specific rules sit parent-owned, 2 generic
   rules sit coding-team-owned) is deferred and optional.
2. **PR #95** — audit says close it, re-land only its rule 2 as ~4 lines, AFTER
   Groups B-D.
3. **Groups B/C/D** — target 354 → 163. **F2 lands LAST.**
4. `~/.claude` branch `harness/reconcile-reference-deploy` @ `cbb8ea2` — **local,
   unpushed**, on top of 5 unpushed harness-map commits. Branched from HEAD, not
   `origin/main`, because `origin/main` there still carries
   `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT: "1"` in `settings.json` — checking it out
   would disarm the write-guard gate in live config. Push from a `~/.claude`-rooted session.
5. `reference/` is not gated by write-guard — `BEHAVIORAL_INSTRUCTION_DIRS`
   (`hooks/write-guard.py:143-150`) omits both `rules` and `reference`.
6. Spec-silence meta-rule — `docs/plans/2026-07-24-spec-silence-meta-rule.md`,
   497 lines, `status: planned`, **31 tasks / 0 executed**, blocked on its Codex gate.
7. `commands/` not in `scripts/deploy.sh` — 22 files, zero matches.
8. Self-modifying hook ticket — `docs/tickets/2026-07-25-...md`, 4 options at
   `:46-54`, **needs the operator**, do not pick.
9. Digest test failure — `skills/second-opinion/scripts/test_build_digest.py::test_design_face_output_is_byte_identical_to_committed_digest`
   fails because the untracked `codex-learnings.d/20260723-...` entry renders into
   the generated digest but is absent from the committed one. Outside
   `pytest hooks/tests`, which is why the baseline reads green. **Operator decides:**
   commit the entry and regenerate, or delete it.

## Operating rules that earned their keep

1. **Dispatch agents WITHOUT `name` when you need the report inline.** Passing
   `name` silently forces background mode and overrides `run_in_background: false`.
2. **`SendMessage` resumes a completed agent from its transcript** and works well
   for revision rounds — used twice here. Latency ~75-90s; useless for steering a
   short task.
3. **Verify every agent state claim by command.** This session the planner
   corrected *me* on a fact I had asserted twice and already written into two
   documents. Agent file-CONTENT analysis is consistently excellent; agent claims
   about working-tree state are guesses. Reject the premise, keep the analysis.
4. **A fresh reviewer for round 2 was worth it** — it found the defect the revision
   introduced, which the original reviewer would have been primed to miss.
5. **Use a FRESH `codex exec` for every round; never `codex exec resume`.** The skill's
   reference suggests resume for plan reviews. This gate did the opposite and it paid for
   itself twice: R2 and R3 each caught a false claim that the PREVIOUS round's fix had just
   introduced — exactly what a primed reviewer waves through. Cost is one extra file read
   per round.
6. **When three rounds of fixes keep regenerating the same defect class, fix the CLAIM, not
   the next instance.** R2/R3/R4 each corrected the mutation-coverage prose and each left or
   created another error in it. The exit was to weaken the claim to what the runs actually
   support and declare the gap. A claim you cannot verify exhaustively should not be made
   exhaustively.
7. **Codex reviews stream ~330KB per round.** Pipe through `tail -c 8000` — the verdict and
   findings are at the end. Piping to `tee` a temp file overflowed the tool-result cap on
   round 1.
