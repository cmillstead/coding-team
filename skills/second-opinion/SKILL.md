---
name: second-opinion
description: "Use when you want an independent second opinion from a different AI model (OpenAI Codex CLI). Three modes: review (pass/fail gate on a plan or diff), challenge (adversarial — actively tries to break your code), and consult (open-ended question to a different model). Use after /review for cross-model coverage, or during Phase 4 planning for independent plan validation. Requires Codex CLI installed: npm install -g @openai/codex"
---

# /second-opinion — Cross-Model Second Opinion

Independent review from OpenAI's Codex CLI. Different model, different blind spots. Overlapping findings are high-confidence. Unique findings from each model are where the second opinion earns its value.

When invoked standalone:
- No arguments: check for active diff (`git diff main --stat`) and review it. If no diff, ask what to review.
- `review`: review current diff or specified plan file
- `challenge`: adversarial mode against current diff
- `consult <question>`: open-ended consultation

When invoked from /coding-team pipeline: the lead specifies mode and target.

For all command examples, iterative revision protocol, and pipeline integration details, see `skills/second-opinion/reference.md`.

---

## Prerequisite: Codex CLI

```bash
which codex 2>/dev/null
```

If not found: inform the user and suggest `npm install -g @openai/codex`. Do NOT proceed without it.

---

## Pre-flight — MANDATORY

You are the quality gate. NEVER dispatch to Codex without completing pre-flight first.

### Step 0: Confirm repo context

Before anything else, verify Codex will review the right codebase:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
echo "Repo: $(basename $REPO_ROOT) at $REPO_ROOT"
```

Confirm the repo name matches the project you're working on. If it doesn't, `cd` to the correct repo root before proceeding. All subsequent `codex` commands MUST run from `$REPO_ROOT`.

### Step 1: Pattern check

1. Read `skills/second-opinion/codex-learnings.md`
2. Check the plan or diff against EVERY anti-pattern in the checklist (all P## and C## entries)
3. Count the total items in the checklist file (highest P## + highest C##). Report ALL items in a coverage line — every ID must appear exactly once in one of three buckets:
   `Pre-flight: ✓(N) C5 C8 C9 | FIXED(N) P1 P10 | N/A(N) C1 C2 C3 C4 C6 C7 ...`
   `Verify: ✓(N) + FIXED(N) + N/A(N) = TOTAL. Highest P=P##, highest C=C##, so total = ## + ## = TOTAL.`
   - **✓** = checked, no issue found (show detail table row)
   - **FIXED** = violation found and fixed before dispatch (show detail table row)
   - **N/A(reason)** = not applicable — must include a one-word reason per item (e.g., `N/A(no-paths) C1 C2`, `N/A(no-SQL) C11 C12`). Bare N/A without a reason is not valid — it's a skip, not a classification.
   The per-bucket counts must be derived by counting the IDs listed in that bucket, not asserted. Show the arithmetic: highest P + highest C = total, then count each bucket's IDs to verify. If the sum doesn't match, you miscounted — recount the IDs in each bucket.
   Known rationalization: reporting a round number that "feels right" instead of actually counting the IDs in each bucket. The N/A bucket is where miscounts hide — count it explicitly.
4. Show a detail table ONLY for ✓ and FIXED items (not N/A — the coverage line proves you considered them)
5. For each FIXED item: fix it in the plan/diff before proceeding
6. Report: `Pre-flight fixed: P1 (phantom field X), P10 (wrong column name Y)` or `Pre-flight: clean`

Only dispatch to Codex AFTER the pre-flight is clean. This catches recurring issues before round 1 — Codex should find novel problems, not the same 20 patterns we already know about.

Known rationalization: "I'll check the patterns during the review" — NO. Pre-flight runs BEFORE dispatch, not during. The whole point is to fix issues before Codex wastes a round on them.

---

## Mode 1: Review (pass/fail gate)

Independent review of a plan or diff. Use `codex review --base main` for diffs, `codex review --uncommitted` for unstaged changes, or `codex exec` for plan files (see reference.md for exact commands).

Always capture output: `2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt`

For plan reviews AND diff/code-fix re-reviews, iterate up to 5 rounds each. For plan reviews, use `codex exec resume`; address each issue with real improvements between rounds. The inter-round verification gate below applies before EVERY re-dispatch on BOTH paths. See reference.md for the iterative-revision protocol (both loops) and the verification gate.

### Inter-round verification gate — MANDATORY

You are the quality gate. After you apply fixes in response to Codex findings — for a plan revision OR a diff/code fix — confirm verification is GREEN via the Bash tool before EVERY re-dispatch to Codex, on every round. Establish a baseline FIRST: run verification BEFORE applying this round's fixes so you can tell a NEW failure from a pre-existing one. If a NEW failure appears (not in the baseline), it is a regression you introduced — fix it locally and re-run before re-dispatching; do NOT spend a Codex round on a regression you can catch locally. If verification stays red ONLY due to pre-existing baseline failures (no new failures from your fixes), do NOT loop indefinitely — STATE which failures are pre-existing vs new and get USER APPROVAL before re-dispatching. If the project has NO runnable test/lint/typecheck command, STATE that and proceed (do NOT silently skip, do NOT block). See reference.md → "#### Verification gate (used by both revision loops)" for command discovery and the full 7-step protocol.

Known rationalizations — these are bypasses, not exemptions:
- "I'll verify at the end" — NO. The gate runs before EACH re-dispatch, not once at the end.
- "The fix was small / a one-liner" — NO. Size does not exempt the gate; it runs every round regardless of fix size.
- "The next Codex round will catch it anyway" — NO. Spending a Codex round on a locally-catchable regression is exactly the waste this gate prevents. Fix it locally first.

### Post-dispatch: Validate findings are in-repo

After Codex returns, before presenting results:

1. Extract every file path from Codex findings
2. Check each path exists in the current repo: `test -e "$REPO_ROOT/<path>"`
3. If ANY finding references a file not in this repo:
   - Flag as **WRONG REPO** — Codex reviewed a different codebase
   - Do NOT present those findings as real issues
   - Re-run with an explicit diff: pipe `git diff main` directly to Codex via `codex exec` instead of relying on `codex review --base main`
4. Report: `Validation: all findings reference files in $(basename $REPO_ROOT)` or `WARNING: Codex reviewed wrong repo — N findings reference paths outside this repo`

### Present results

```
## Codex Review
**Verdict:** PASS | FAIL | APPROVED | REVISE
**Findings:**
- [P1] file:line — description
- [P2] file:line — description
**Overlap with Claude review:** (if /review or audit has also run)
- [finding] — flagged by both (high confidence)
**Codex-only findings:**
- [finding] — investigate
**Claude-only findings:**
- [finding] — investigate
```

### Cleanup
```bash
rm -f /tmp/second-opinion-review-${REVIEW_ID}.txt
```

---

## Mode 2: Challenge (adversarial)

Codex actively tries to break your code via `codex exec` with an adversarial prompt. Tests for: crash inputs, state corruption sequences, race conditions, validation bypasses, untested edge cases.

See reference.md for the full adversarial prompt template.

Present results grouped by severity. P1 findings are blockers. P2 must be addressed before proceeding.

### Cleanup
```bash
rm -f /tmp/second-opinion-challenge-${REVIEW_ID}.txt
```

---

## Mode 3: Consult (open-ended)

Ask Codex an open-ended question about the codebase via `codex exec`. For follow-ups, use `codex exec resume ${CODEX_SESSION_ID}` to maintain conversation context.

### Cleanup
```bash
rm -f /tmp/second-opinion-consult-${REVIEW_ID}.txt
```

---

## Model Selection

Default: Codex CLI default model (no `-m` flag). User can override with `-m MODEL`:
- `/second-opinion review o4-mini` — cheaper, faster
- `/second-opinion challenge o3` — maximum reasoning for adversarial mode

If default returns low-quality results, suggest retrying with a stronger model.

---

## Cross-Model Analysis

When both Claude and Codex have reviewed the same code, produce a cross-model analysis showing consensus findings, Codex-only findings, Claude-only findings, and disagreements. See reference.md for the full template.

---

## Post-Review: Learning Capture

After every Codex review that produces findings (any mode), before cleanup:

1. Read `skills/second-opinion/codex-learnings.md`
2. For each finding Codex raised: does it match an existing pattern (any existing P## / C## entry)?
   - **Yes**: no action — pre-flight should have caught it. If it didn't, check why pre-flight missed it and tighten the pattern description.
   - **No**: is this a one-off or a recurring class of mistake?
     - **One-off** (project-specific logic error): skip
     - **Recurring** (would apply to other plans/code): append to the appropriate table in `codex-learnings.md` with the next ID (P16, C15, etc.)
3. Report: `Learning capture: added C15 (<name>)` or `Learning capture: no new patterns`

---

## Rules

- `codex review` is read-only. `codex exec` in challenge/consult has full access but is used only for analysis.
- Always use session-scoped temp file paths (UUID prefix) to prevent conflicts
- Capture output with `2>&1 | tee /tmp/second-opinion-*.txt` — there is no `-o` flag
- Reuse Codex session ID for multi-round reviews via `codex exec resume SESSION_ID`
- **Verification gate every round:** after applying fixes in response to Codex findings, confirm verification (test/lint/typecheck, via the Bash tool) is GREEN before EACH re-dispatch to Codex — every round, regardless of fix size. Baseline first, then distinguish a NEW failure (fix locally) from a pre-existing one (state it, get user approval — do NOT loop). No runnable command → state and proceed. Applies to ANY re-dispatch after applying fixes (plan-revision, diff/code-fix, or re-challenge). See Mode 1 and reference.md.
- If a Codex revision contradicts user requirements, skip that revision and note it
- Clean up temp files after every invocation
- Never present Codex's output as Claude's own analysis — always attribute clearly
- **ALL findings must be addressed** — fix, defer with user approval, or explain why it's a false positive. "Pre-existing" is NOT valid to skip a finding.
- After completing any review or challenge (after presenting findings and any required fixes), update the active plan file's Completion Checklist. The active plan is the unique file under `$(git rev-parse --path-format=absolute --git-common-dir | sed 's|/.git$||')/docs/plans/*.md` whose frontmatter contains `status: in-progress`. If zero or more than one plan claims `status: in-progress`, fail closed and ask the user to resolve before re-running `/second-opinion`.

  Edit the plan file: change `- [ ] Second-opinion review` to `- [x] Second-opinion review`. If you ran an adversarial challenge, add a parenthetical note: `- [x] Second-opinion review (challenge: <one-line summary>)`. The coding-team lifecycle hook reads this checkbox to enforce the gate; without the edit the pipeline will block at completion.

  If no active plan file is found (standalone `/second-opinion` invocation outside a coding-team session), skip this step — there is nothing to gate.
