# Handoff — F1 surface-measurement: IMPLEMENTED & LIVE, one gate left (2026-07-26, updated 2026-07-27)

> **Filename is now slightly misleading** — it says `plan-ready`, but the plan is
> executed. Kept as-is so existing references keep resolving; the content below is
> authoritative over the filename.

Supersedes nothing. Companion to `2026-07-26-saturation-remediation-phase1-complete.md`,
which is still accurate for everything outside this plan. Every state claim below
was verified by command at write time.

---

## ► RESUME HERE — one gate left, then Phase 6

**Phases 1-5 are DONE. The feature is IMPLEMENTED, TESTED, DEPLOYED, and LIVE.**
The Codex *plan* gate closed APPROVED after 5 rounds — **do NOT re-run it**, and do
NOT re-plan or re-dispatch Tasks 1-4. All four landed and were verified by command.

**The single remaining action is Phase 5 exit gate 4: the post-execution Codex
`review` (mode `review`, NOT `plan`), over `git diff main..HEAD`.** Gates 1-3 are
closed (see "Phase 5 exit gates" below).

After that gate passes:
1. Set the plan's frontmatter to `status: complete` — **this is what disarms
   `hooks/write-guard.py`**, which is currently ARMED. See the ARMED warning under
   "Repo state" before touching any instruction file outside the two declared paths.
2. Phase 6: choose merge / PR / keep-branch / discard.

**State at handoff:** 5 code+docs commits landed on top of the 4 pre-existing docs
commits; nothing is half-applied; no mutation survives anywhere (verified by
`git diff` after every mutation round). The working tree holds **three** entries,
and **none may ever be staged**: `.claude/settings.local.json` (modified,
pre-existing), `docs/handoff/2026-07-26-f1-surface-measurement-plan-ready.md`
(modified — THIS file, in flight), and the untracked
`skills/second-opinion/codex-learnings.d/20260723-...` entry (pre-existing).

**Verified after the final commit `92a0c78`:** `python3 -m pytest hooks/tests -q` →
**1067 passed, 9 skipped**, exit 0. `ruff check .` → clean. Live probe
`echo '{}' | python3 ~/.claude/hooks/hook-health-check.py` → `exit=0`,
`"decision": "allow"`, reason contains
`Always-loaded surface is 354 lines (threshold: 200)`.

*(Suite arithmetic, for anyone re-deriving it: BASELINE 1055 → +10 Task 1 → +1
Task 2 → +1 the broken-symlink test in `92a0c78` = 1067.)*

---

## Repo state

- **Branch:** `feat/always-loaded-surface-measurement`, cut from synced `main` @ `0998201`. **Nine commits.** Four docs-only, from before execution: `60f4e40` (this handoff, created), `6668993` (gate APPROVED + pre-flight corrections), `7aaf725` (write-guard ARMED warning), `4572c27` (reconciled 7 stale claims). Then the five from Phase 5:

  | SHA | Task | Contents |
  |---|---|---|
  | `3869805` | 1 | `ALWAYS_LOADED_THRESHOLD`, `_count_lines()`, `check_always_loaded_surface()`, 10 tests. Function left deliberately unwired |
  | `64cd331` | 2 | Wired into `main()` (call + early-return conjunct + output block), `main()`-level integration test, reason-allowlist entry, deployed |
  | `6f4b38e` | 3 | Corrected F3's prescription + both falsified Appendix B rows in the audit report |
  | `bcd381d` | 4 | Recorded F1 as landed in the Phase-1 handoff; corrected its stale symlink count |
  | `92a0c78` | QA fixes | Four defects the QA gate found in the above — see "QA findings" below |
- **`main`** @ `0998201`. Merged today: #118–#124.
- **⚠ `write-guard.py` is now ARMED — deliberately.** As of Phase 5 pre-flight,
  `docs/plans/2026-07-26-always-loaded-surface-measurement.md` carries
  `status: in-progress` (verified: it is the ONLY plan that does). This is the
  intended state for the duration of Phase 5, **not** stale frontmatter.
  **Do NOT "clean it up" to unblock an edit.** Instruction/hook edits to the two
  paths declared in its `instruction_files:` are permitted; edits to any OTHER
  instruction file will be blocked, and that is correct — declare the path in the
  plan's `instruction_files:` rather than working around the guard. **Never set
  `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`** — it disarms the whole session.
  The plan returns to `status: complete` at the end of Phase 5, which disarms it.
- **Working tree carries two pre-existing not-ours files** — `.claude/settings.local.json`
  (modified) and untracked `skills/second-opinion/codex-learnings.d/20260723-...-self-heal-migration-schema-shape.md`.
  **Never stage either.** The second is a live C27 learning entry AND the cause of
  the digest test failure (see "Known failures").
- **Verified current state:** `python3 -m pytest hooks/tests -q` → **1067 passed,
  9 skipped** (was 1055 before execution). `ruff check .` → clean.

## Phase 5 exit gates — 3 of 4 CLOSED

| # | Gate | Status |
|---|---|---|
| 1 | Full-suite test + lint | ✅ 1067 passed / 9 skipped, ruff clean, run after the final commit |
| 2 | `ct-qa-reviewer` | ✅ **PASS**, zero P1s. 7 findings — 4 fixed in `92a0c78`, 3 deferred (below) |
| 3 | Doc-drift scan | ✅ One finding: THIS handoff was stale. Fixed by the edit you are reading. No other tracked doc drifted |
| 4 | Post-exec Codex `review` | ❌ **NOT RUN — this is the resume point** |

**Gate 2 confirmed the things most worth confirming:** the dark feature Task 1
deliberately left IS closed (`check_always_loaded_surface` → called at `:731` →
emitted at `:764-768` → survives the early return at `:739-741` → `allow_with_reason`
→ dispatcher envelope-unwrap → user); no path in the diff can produce a block; the
new test class did NOT copy the vacuous inline-glob pattern from
`TestCheckInstructionFileLengths`; and every doc number (238 / 116 / 7 files / 354 /
2 symlinks + 5 regular / 61 across 3) checks out independently.

## QA findings — 4 fixed, 3 deferred to the reduction phase

**Fixed in `92a0c78`** (all four were introduced by this session's own commits, so
none was eligible for deferral):
1. Two `file:line` citations in a committed docstring pointed at unrelated code
   (`:667` is `parts = []`, not `allow_with_reason`, which is at `:779`; the
   `HOOKS_DIR.is_dir()` guard is `:688-689`, not `:589-590`). Now cite the SYMBOL
   name first, line second — this file has drifted twice.
2. **The `mock-ok:` markers were leaving two lines permanently unguarded.**
   `write-guard.py:628-631` exempts the marker's own line AND the following line, so
   `:466`/`:677` were dead zones in this repo's flagship no-mocks test file. Root
   cause was prose containing the literal word `monkeypatch` while explaining it is
   NOT used. Rewriting it as `monkey-patching` defeats the `\bmonkeypatch\b` regex,
   so both markers were deleted and the guard restored. **`grep -c "mock-ok"` → 0.**
3. A broken symlink under `rules/` was counted in `len(rules_files)` while
   contributing 0 lines ("116 lines across 8 file(s)"). Unreadable entries are now
   excluded from the count and reported as `(N unreadable)`. New test + mutation proof.
4. The docstring claimed the sum "is the cost a session actually pays" — false.

**Deferred — these BLOCK Groups B/C/D, not this merge:**
1. **`MEMORY.md` is unmeasured.** `~/.claude/projects/<slug>/memory/MEMORY.md`
   (64 lines today, grows with every feedback memory) also auto-loads into every
   session. True surface is ~418, not 354. Folding it in makes the number
   project-dependent, which is a real design cost — **this is a scope decision for
   the operator, not a bug.** The docstring now names it as a known-unmeasured
   contributor and calls the reported number a floor.
2. **The audit's reduction arithmetic does not reconcile.** Group subtotals
   (−110/−42/−93/−44/+12) sum to **187**, not the **163** printed as the target at
   `docs/reports/2026-07-26-claudemd-saturation-audit.md:280` and `:19`. Every
   subtotal is internally correct; the 24-line gap is in the roll-up. Combined with
   item 1, the claimed "37 lines of headroom" is actually negative. **The bad number
   is already propagated into `2026-07-26-saturation-remediation-phase1-complete.md:113`
   ("Target 354 → 163"), which is what the next phase will execute against.**
3. **The audit report is half-corrected.** `6f4b38e` adopted correct-inline-with-a-
   dated-note for F3 and Appendix B, but the same document still carries unmarked:
   `:6` "all 12 rules" (now 7), `:15`/`:19`/`:22`/`:137-138` "464" (now 354), `:111`
   "226 lines" (now 116), and **§5 Group A has no LANDED marker** while `:270-281`'s
   arithmetic still assumes it is pending. Pick ONE convention for the document.

**One resume trigger worth setting:** `main()`'s early-return conjunct
(`hook-health-check.py:739-741`) is inert in BOTH environments today, because
`check_instruction_file_lengths()` is never empty at either root. It becomes
load-bearing at exactly the moment the reductions succeed and the surface warning is
the only remaining signal. **When `check_instruction_file_lengths()` first returns
`[]`, re-verify that conjunct by mutation** — until then it is inspection-only.

## The plan

`docs/plans/2026-07-26-always-loaded-surface-measurement.md` — **1152 lines,
`status: in-progress` (ARMED — see the warning under "Repo state"), gitignored**
(`.gitignore:2`, so it will never be committed). **Set it to `status: complete` once
gate 4 passes; that is what disarms the write-guard.** It grew 1028 → 1152 during the
5-round Codex gate; almost all of that is prose about its own test coverage, not
about the change, which is still one function + one helper + one constant + ~7
lines of wiring.

```yaml
instruction_files: hooks/hook-health-check.py, hooks/tests/test_hook_health_check.py
```

Both reviewers independently confirmed this declaration is complete AND minimal.
`docs/*` is not gated; `scripts/deploy.sh` is executed, not edited.

**All 4 tasks are EXECUTED and committed** — see the commit table under "Repo state"
for what each one landed. Task 4 was dispatched at `sonnet` rather than the plan's
`haiku`: its Step 3/4 required re-deriving literal `old_string`s from a hard-wrapped
file rather than copying them from the brief, and its Step 6 had become the plan's
final whole-plan verification gate. That is judgment, not mechanical replacement.

Every mutation table was performed in full — 12 rows in Task 1, 2 in Task 2, 1 for
the QA fix — each restored and confirmed by `git diff`. **Mutation 7 (repo-rooting
the default) did turn `test_default_target_is_the_deployed_home_dir` RED**, which is
the one result that proves the deployed-path guard is real rather than prose.

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

**The audit's own F1 prescription was rejected in the plan**, on two independent
grounds — reproduce BOTH; the gate spent two rounds getting the first one right:
1. `repo_root = Path(__file__).parent.parent` is NOT symlink-resolved, so it is
   `~/.claude` for the deployed hook but this repo under pytest. A `rules/*.md` glob
   added there measures the deployed 7 files (116 lines) in production but this
   repo's 3 (**61** lines, including a `README.md` that is never deployed) under
   pytest — two different file sets, and no test could pin the production one.
   **Do not write "37" in this argument**: 37 is the deployed share this repo OWNS
   (its 2 symlinked rules), a different quantity. That conflation was a finding twice.
2. It is a PER-FILE check, so a 200-line threshold never fires on 5-29-line rules
   at any root. This reason alone is sufficient.

Current surface: **354** = `~/.claude/CLAUDE.md` 238 + `~/.claude/rules/` 116.

**This is a WARNING, never a block.** It fires immediately at 354 and that is
intended. A blocking cap is audit finding **F2, which must land LAST**, after the
reductions — at 238 lines a cap that blocks >200 would block the very edits that
reduce it. The plan carries a dedicated "this is NOT F2" comparison table.

## Codex plan gate — corrected pre-flight (record only; the gate is CLOSED)

**The actionable resume steps are the "► RESUME HERE" block at the top of this file.
This section is the gate's record, not a to-do list.** An earlier version of this
section duplicated the resume steps and told you to flip the plan to `in-progress` —
that is already done, and following it again would have been harmless but confusing.

**The audit line in the previous version of
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
coverage gap, verified by inspection only** — see the Failure Modes row for
`main()` / Step 3's conjunct (the plan grew to 1152 lines during the gate, so grep
for `and not surface_warnings` rather than trusting a line number). Do not
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
  `Tested? Yes` for a regression no test could observe — every aggregate test then
  written passed `claude_dir=` explicitly and was blind to the default. (The class
  was 8 tests at that point and is 10 now; `test_default_target_is_the_deployed_home_dir`
  is still the only one that observes the default.)
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
3. **Groups B/C/D** — **the 163 target does not reconcile; do NOT execute against it
   until it is recomputed.** The group subtotals sum to 187, and the unmeasured
   `MEMORY.md` adds ~64 more — see deferred findings 1 and 2 above. **F2 lands LAST.**
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
