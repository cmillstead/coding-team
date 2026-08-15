# Handoff — output-style translation pointer, cross-repo remainder

**Date:** 2026-08-14
**Branch (coding-team repo):** `harness/output-style-translation-pointer`
**Status of this session's work:** COMPLETE and verified. This handoff covers only what could NOT be done from a session rooted at `/Users/cevin/.claude/skills/coding-team`.

---

## The task

The user's active output style (`~/.claude/output-styles/eli5.md`, selected at `~/.claude/settings.json:185`) is correctly configured and IS loaded. The config was never broken. The defect is compliance: the orchestrator relays subagent reports, review verdicts, severity codes, hook errors, and raw tool output verbatim into user-facing replies instead of translating them into the active output style's voice.

The fix: state the rule ONCE in `reference/user-facing-translation.md`, and place a one-line pointer to it at each place the orchestrator writes a user-facing report.

**User constraints, both explicit:**
- **No hook.** The user forbade a hook for this. Do not create one.
- **Only the relevant skills.** Do not pad the include-set. The bar is: the ORCHESTRATOR presents subagent output, tool output, verdicts, severity codes, or hook errors TO THE USER in chat. Writing a report FILE does not count.

---

## What is already done (do not redo)

Committed on branch `harness/output-style-translation-pointer` in `/Users/cevin/.claude/skills/coding-team`:

| Commit | What |
|---|---|
| `675bbeb` | Created `reference/user-facing-translation.md` (49 lines) |
| `8dbe7be` | Pointer in `skills/second-opinion/SKILL.md` |
| `b6082c0` | Pointer in `skills/debug/SKILL.md` |
| `8fe62ec` | Pointer in `skills/prompt-craft/SKILL.md` |
| `7376062` | Pointer in `phases/completion.md` |
| `d6b34e1` | Pointer in `phases/ci-fix-protocol.md` |
| `819bfeb` | QA fixes: moved completion pointer above the tier gate, added `phases/audit-loop.md` pointer, closed two rule gaps |
| `3d13b6a` | Pointers in `skills/dep-audit`, `skills/a11y`, `skills/api-qa`, `skills/incident` |
| `9f450e8` | Moved `phases/audit-loop.md` pointer above the budget-check report (reachability) |
| `dc47260` | Hoisted `second-opinion` and `incident` pointers above ALL reporting paths (reachability) |

**10 pointer sites total, each containing the pointer exactly once. Verified.**

The reference file is deployed as a relative symlink at `~/.claude/reference/user-facing-translation.md` → `../skills/coding-team/reference/user-facing-translation.md`. `scripts/deploy.sh:103` globs `reference/*.md`, so no deploy.sh change was needed and none was made.

**The canonical pointer line, byte-identical at 9 of 10 sites:**

```
Read ~/.claude/reference/user-facing-translation.md before writing this report to the user.
```

The exception is `phases/audit-loop.md:59`, which reads `...before writing any of the user-facing reports in this section.` because that section has more than one user-facing moment. This wording difference is deliberate — do not normalize it.

---

## REMAINING WORK — 3 files in the `~/.claude` repo

These have confirmed user-facing report moments and are **tracked by `~/.claude`, not by the coding-team repo**.

| File (relative to `~/.claude`) | Line | The report moment |
|---|---|---|
| `skills/_scan-common/phases/output.md` | 130 | `### 4d — Report to user` — *"Print a summary to the conversation… **Severity totals**: table of CRIT/HIGH/MED/LOW counts"* |
| `skills/scan-fix/SKILL.md` | 147 | Step 4 final report — `Fixed: N findings (N CRIT, N HIGH, N MED, N LOW) via N dispatched fix-agents` |
| `skills/adopt/SKILL.md` | 47 | *"**Confirm gate (default):** present the verdict + the exact install/rewrite you propose, and get a 'go' before writing."* |

**`_scan-common/phases/output.md` is the high-value one.** All five `scan-*` skills (`scan-code`, `scan-product`, `scan-security`, `scan-previous`, `scan-adversarial`) route their user reporting through it and add only vault titles and filenames — `scan-product` even says *"In the user report (Phase 4d), additionally include:"*. **One pointer there covers all five skills.** Do not add pointers to the five individually; they are excluded-as-covered.

### Why a separate session is required (technical, not conventional)

1. `hooks/write-guard.py`'s `check_phase5` resolves the active plan from **the repo that owns the target file**, never from the process working directory. The coding-team plan's `instruction_files:` allowlist therefore cannot authorize an edit to a file owned by `~/.claude`.
2. `~/.claude` has one writer at a time, and a session stays in the directory it started in.

**So:** start a session rooted at `/Users/cevin/.claude`, write a plan there declaring those three paths under `instruction_files:`, and apply the same pointer line.

No ordering dependency remains — the reference file is already created, committed, and deployed, so `~/.claude/reference/user-facing-translation.md` resolves right now.

### Landmines for that session

- **`instruction_files` is ONE comma-separated line, not a YAML list.** `hooks/_lib/active_plan.py:482` parses it with `raw.split(",")`. Entries must be repo-relative. A leading, trailing, or doubled comma raises `MalformedInstructionAllowlistError` and fails closed, blocking every instruction-file edit.
- **`skills/scan-fix/SKILL.md` and `skills/adopt/SKILL.md` are `SKILL.md` files**, so `check_skill_line_cap` applies: `hooks/write-guard.py:766` sets a **hard block** at >200 lines, and the pattern `\.claude/skills/.*/SKILL\.md$` matches them. Check `wc -l` BEFORE editing. If a file is at 199 or 200, offset the insertion by removing a cosmetic separator in the same round — do NOT set `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`.
- **`_scan-common/phases/output.md` is not a `SKILL.md`**, so the hard cap does not apply; only the `hook-health-check.py:256` warning at >200 lines.
- **Do not add anything to `~/.claude/rules/`.** Everything there loads unconditionally into every session AND every subagent. `rules/README.md:9-24` names the exact rationalization to avoid.
- **Do not edit `~/.claude/CLAUDE.md`.** See the decision below.

---

## ALSO OPEN — `harness-map` (a third repository)

`~/.claude/skills/harness-map` is a symlink to `/Users/cevin/src/harness-map`, tracked by neither `~/.claude` nor coding-team. It has a real report moment at `## Report Contract — 6 Sections` (line 73 of its `SKILL.md`).

Flagged only. Needs its own session rooted at `/Users/cevin/src/harness-map`. Lowest priority of the four.

---

## Decisions made — do not re-litigate

**1. `reference/`, not `rules/`.** `rules/*.md` loads unconditionally into every session and every subagent; `reference/*.md` loads only when a prompt names it. `rules/README.md:9-24` is authoritative and names the rationalization ("extracting duplicated agent-prompt text into `rules/` de-duplicates it") that must not be repeated. It converts per-agent cost into global cost.

**2. `~/.claude/CLAUDE.md` is NOT edited — not even to add a Reference Pointers entry.** Its Working Style line already states the rule and remains the single top-level statement. A pointer there would grow the always-loaded surface, reversing a completed arc that cut it from 464 lines to 190. More importantly, that line is *already* always-loaded and *already* being ignored at the reporting moment — that is the entire defect. A second always-loaded mention adds cost and changes nothing. What was missing is a reminder at the moment of reporting.

**Accepted trade-off, stated openly:** the reference file is not listed in CLAUDE.md's Reference Pointers section, so a reader scanning that list alone will not discover it. Intentional — it is reached from the skills that need it, not browsed. Do not "fix" this.

**3. The rule binds the ORCHESTRATOR only.** Worker agent prompts (`agents/*.md`) keep producing dense structured reports — that output is INPUT to the translation step. Pushing this rule into worker prompts would corrupt the report formats the pipeline parses. The reference file states this exclusion internally.

**4. The rule is output-style-agnostic.** It never names ELI5 and would keep working if the user switched styles. Verified both ways: the check pattern returns 3 on `~/.claude/output-styles/eli5.md` and 0 on the reference file. Preserve this — do not hardcode the current style's filename anywhere in the rule.

---

## Verification state at handoff time

All run fresh in-session, not asserted from memory:

- Full repo test suite (`python3 -m pytest -q` from the repo root): **1244 passed, 18 skipped, 0 failed**. Run with `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT` and `WRITE_GUARD_ALLOW_PHASE_SKIP` scrubbed from the environment, so the guard was genuinely armed.
  - **Correction, recorded deliberately:** earlier reports in this session said "full test suite, 1205 passed" while actually running only `hooks/tests/` (1205 tests). The real repo suite is 1262 collected. The Codex gate surfaced the gap. Anyone resuming should run `python3 -m pytest -q` from the repo root, not `pytest hooks/tests/`.
  - One pre-existing failure (a stale design digest) was found and cleared with the user's approval — see below.
  - `hooks/tests/test_posttooluse_dispatcher.py::TestCodesightQueryLogging::test_usage_log_grows` failed once under concurrent agent load (it asserts a shared usage log grew; several agents were writing to it simultaneously) and passes in isolation and on the final full run. Flaky by construction, not a regression from this work. Left alone because the plan forbids touching `hooks/`.
- Rule text exists in exactly **one** file (`grep -rl "Both halves are required"`).
- All 10 pointer sites contain the pointer exactly once — no misses, no duplicates.
- Zero pointer occurrences under `agents/` or `rules/`.
- No `skills/*/SKILL.md` in the coding-team repo exceeds the 200-line hard cap.
- `~/.claude/rules/` untouched; `~/.claude/CLAUDE.md` untouched by this work.

### OPEN — stale design digest (pre-existing, needs a decision)

`skills/second-opinion/scripts/test_build_digest.py::test_design_face_output_is_byte_identical_to_committed_digest` FAILS. The committed design digest is missing the `**C30:**` and `**C31:**` design-default lines that `render_digest` produces from the real entries directory.

Cause: `skills/second-opinion/codex-learnings.d/20260806-023926-0636-literal-scan-misses-var-pairs.md` (entry C31) is **untracked** and predates this session — it was already in `git status` at session start. The digest was never rebuilt after that entry and C30 landed. This branch touched neither `codex-learnings.d/` nor the digest (`git diff --name-only origin/main...HEAD` confirms).

**RESOLVED with the user's explicit approval** — commit `b2d5a3f`. The digest was regenerated via its own entry point (`python3 skills/second-opinion/scripts/build-digest.py`), never hand-edited, and the C31 entry file was committed in the SAME commit.

Both had to land together: committing only the rebuilt digest would leave a fresh clone rendering a digest WITHOUT C31 (its source file being untracked), failing the identical test inverted. Committing only the entry file would leave the digest stale. The C31 entry was checked first and carries all three required elements — an `# C31` H1, an `@tags:` token, and a `**Design default:**` line.

Proven both ways rather than assumed: the test was run BEFORE the rebuild (FAILED) and after (PASSED).

Note for reviewers: this commit is unrelated to the output-style work and rides along only to leave the branch green. It is a clean single commit if it needs to be split out.

### Cross-model review (Codex) — findings and dispositions

Codex `review --base origin/main` returned 2 × P2, both the SAME reachability class already fixed twice locally. Both FIXED in `dc47260`:

1. `skills/second-opinion/SKILL.md` — the pointer sat inside Mode 1's `### Present results`. Modes 2 (challenge) and 3 (consult) are one-line stubs delegating to `reference.md` and never execute that step, yet both present severity-tagged model output. Pointer was dead for two of three modes. Hoisted to line 18, above all three `## Mode` headings, with wording naming all three modes.
2. `skills/incident/SKILL.md` — the pointer sat inside `## Post-Mortem Protocol`. The active-incident path (`## Severity Classification` SEV1–SEV4 table, `## Active Incident Protocol` stakeholder and status updates) runs entirely above it and never arrives. Hoisted to line 10, above all three sections.

**Reachability is now traced across all 10 sites.** Four had the defect (`phases/completion.md`, `phases/audit-loop.md`, `skills/second-opinion/SKILL.md`, `skills/incident/SKILL.md`); six were clean. **If more pointers are added — including the three cross-repo ones — trace this explicitly:** list every user-facing moment in the file and confirm the pointer precedes ALL of them, not just the nearest one. This defect class recurred four times; assume the fifth is waiting.

### Pre-existing condition, unrelated to this work

`~/.claude/CLAUDE.md` has an **uncommitted** modification already present before this session: a one-line addition to the "Commit style" bullet about milestones/phases/stages starting at 1 rather than 0. It is not ours — CLAUDE.md was never in this plan's allowlist, so the armed write-guard would have blocked any agent that tried. Worth committing or reverting deliberately; it is currently sitting uncommitted in the always-loaded config.

---

## QA findings — dispositions

A feature-level QA review returned PASS_WITH_CONCERNS with 10 findings. All 10 are accounted for.

**Fixed (6):**
1. `phases/completion.md` pointer sat below a "Trivial: SKIP" gate and below the raw-test-output step — moved to line 13, above every tier gate and above the output paste. Fires on all paths now.
2. Broken referent in the reference file ("This sentence" had no antecedent) — rewritten as "The quoted sentence above…".
3. Rule had no clause for reports that are also written to disk and parsed by later phases (`debug` → `docs/debug/`, completion summary → `retrospective`) — clause added.
4. Rule had no clause for blocks a skill instructs you to print VERBATIM (`phases/completion.md:188`) — clause added.
5. Rule dropped CLAUDE.md's "tool-call or not" qualifier, the loophole where a short status beside a tool call goes untranslated — restored.
6. `phases/audit-loop.md:59` (*"surface to the user with the BLOCKED reason"*) was never surveyed at all — pointer added.

**Fixed after user approval (4):** `dep-audit`, `a11y`, `api-qa`, `incident` — the original 21-item survey never evaluated 15 of this repo's own 21 skill files. These four clear the same bar the first five did. The other 11 were checked and do not.

**Accepted, not fixed (4, with reasons):**
- `phases/ci-fix-protocol.md:14` success path reports a PR URL and short summary, exits before reaching the pointer. One link, no verdicts or severity codes.
- `skills/second-opinion/SKILL.md:129` has a user-facing line four lines above the pointer — same reporting region, effectively in context.
- Removing the cosmetic `---` from `second-opinion` (the line-budget offset) leaves `## Model Selection` without a preceding rule. Cosmetic; the offset had to come from somewhere.
- No worked example in the reference file. The file's value is being short, and an example risks baking one style's voice into a deliberately style-agnostic rule.

---

## Next steps, in order

1. Open the PR for `harness/output-style-translation-pointer` in the coding-team repo (if not already done) and check CI.
2. Start a session rooted at `/Users/cevin/.claude`. Write a plan declaring the three paths above under `instruction_files:`. Apply the same pointer line. Highest value first: `skills/_scan-common/phases/output.md`.
3. Optionally, a session rooted at `/Users/cevin/src/harness-map` for its report contract.
4. Decide what to do with the uncommitted `~/.claude/CLAUDE.md` change noted above.

---

## Where things are

- **Plan:** `/Users/cevin/.claude/skills/coding-team/docs/plans/2026-08-14-output-style-translation-pointer.md` — gitignored by `.gitignore:2`, lives on disk only, never enters the PR. Contains the full 21-item traceability table and design rationale.
- **The rule:** `/Users/cevin/.claude/skills/coding-team/reference/user-facing-translation.md`
- **Deployed symlink:** `/Users/cevin/.claude/reference/user-facing-translation.md`
- **This handoff:** `/Users/cevin/.claude/skills/coding-team/docs/handoff/2026-08-14-output-style-translation-cross-repo.md`
