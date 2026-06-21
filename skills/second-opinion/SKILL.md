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

### Step 1: Pattern check — scope by applicability

You are the quality gate. Read the drop-folder (Read tool): first `skills/second-opinion/codex-learnings.d/_header.md` (tag vocabulary, grep battery, audit-line format, banned rationalizations), then every `skills/second-opinion/codex-learnings.d/*.md` EXCEPT `_header.md` (glob the directory — each file is one entry). Signal tokens you emit MUST come from the closed category enum in `_header.md` — off-list ⇒ unread. The **live count** for the audit-line `total:` = number of entry files read (exclude `_header.md`).

Run this engine ONCE per change:

1. **Read** `codex-learnings.d/_header.md` (tags + battery + audit format + rationalizations), then read every entry file in `codex-learnings.d/` excluding `_header.md`.
2. **Derive signals once.** Set `mode` = `diff` (a diff) or `plan` (plan prose). For each `provable`
   category, run its grep battery over the diff hunks (DIFF) or plan prose (PLAN) with the Bash tool.
   A signal FIRES if ANY pattern matches; record it with evidence. Batteries are broad on purpose —
   an over-match costs a cheap `✓`; an under-match risks a silent skip.
3. **Classify every live entry into exactly TWO buckets** (enumerate the live file — do NOT assume a
   fixed count). An entry is **dismissed** for EXACTLY ONE of two reasons; everything else is
   **applicable**:
   - **dismissed(scope-mismatch)** — the entry's `scope:` EXCLUDES the current `mode` (`scope:diff`
     in a `plan` review, or `scope:plan` in a `diff` review). Record `N/A(scope-mismatch:<entry-scope>
     vs mode:<plan|diff>)`. `scope:both` is NEVER scope-dismissed. Scope is checked FIRST.
   - **dismissed(no-signal)** — in scope (scope matches mode or `both`) AND a `provable` category
     whose battery CONFIRMED its signal absent. Record `N/A(no-signal:<cat>, evidence:<grep>)`.
   - **applicable (deep-checked)** — EVERYTHING ELSE: in-scope fired signal, `reasoning-shape`,
     `floor`, untagged/newly-appended, or UNKNOWN/ambiguous derivation.
4. **Floor-default (KEYSTONE):** for an IN-SCOPE entry, deep-check UNLESS it has a valid tag AND its
   non-applicability is grep-provable AND the grep confirmed absence. Untagged/`reasoning-shape`/
   UNKNOWN ⇒ floor — the safe direction is the default. Scope-mismatch precedes this: a `floor` entry
   in matching scope is ALWAYS applicable, but a `scope:plan` floor (P1–P4) is correctly
   scope-dismissed in a pure `diff` review (a diff names no plan-prose symbols).
5. **Deep-check each applicable entry** via its "Check before dispatch" steps. Pull in any LIVE
   "Pairs with …" cross-referenced entry (skip a ref to a non-live ID) (G-xref). For
   `reasoning-shape`, reading-to-rule-out IS the deep-check — record `✓`, never a dismissal.
6. **Fix every FIXED item** in the plan/diff before dispatch.
7. **Emit the audit line** in the `## Audit-line format` shape from `_header.md`. Every live
   entry appears exactly once across `applicable` + `dismissed`; `N + M` MUST equal the live count
   (computed, not hardcoded). If it doesn't, an entry was dropped — recount and re-emit.

**Escalate to a FULL check (deep-check the entire live set)** when ANY holds (G-empty/G-escalate):
the applicable set is empty but the change has ≥1 non-comment code line; the diff mixes languages; or
signal derivation is ambiguous. A markdown-heavy diff NEVER dismisses its code hunks — derive from
the code hunks independently (G-mixed).

**Plan-only reviews** run on PROSE (no diff): the `plan`+`both` set applies, P1–P4 always floor, and
`reasoning-shape` plan entries (P30/P32/P33) are ALWAYS applicable (floor) — reading the prose to
rule one out is its deep-check (recorded `✓`), never a dismissal. The efficiency win is primarily on
DIFF reviews.

Known rationalization: "bulk-dismiss this whole category" — BANNED. Every entry is accounted for BY
ID; dismiss an individual `provable` entry only with a confirmed-absent grep cited as evidence. See
the full banned-rationalizations block in `_header.md`.

Only dispatch to Codex AFTER the pre-flight is clean — Codex should find novel problems, not the recurring patterns in `codex-learnings.d/` already encode.

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

Adversarial mode — see reference.md → Mode 2: Challenge.

---

## Mode 3: Consult (open-ended)

Open-ended consultation — see reference.md → Mode 3: Consult.

---

## Model Selection

See reference.md → Model Selection.

---

## Cross-Model Analysis

See reference.md → Cross-Model Analysis.

---

## Post-Review: Learning Capture

See reference.md → Post-Review: Learning Capture.

---

## Rules

- `codex review` is read-only. `codex exec` in challenge/consult has full access but is used only for analysis.
- Always use session-scoped temp file paths (UUID prefix) to prevent conflicts
- Capture output with `2>&1 | tee /tmp/second-opinion-*.txt` — there is no `-o` flag
- Reuse Codex session ID for multi-round reviews via `codex exec resume SESSION_ID`
- **Verification gate every round:** after applying fixes in response to Codex findings, confirm verification (test/lint/typecheck, via the Bash tool) is GREEN before EACH re-dispatch to Codex — every round, regardless of fix size. Baseline first, then distinguish a NEW failure (fix locally) from a pre-existing one (state it, get user approval — do NOT loop). No runnable command → state and proceed. Applies to ANY re-dispatch after applying fixes (plan-revision, diff/code-fix, or re-challenge). See Mode 1 and reference.md.
- **Emit run telemetry on every Mode 1 review:** after presenting a `PASS|FAIL|APPROVED|REVISE` verdict from a plan or diff review — **including a clean pass with zero findings** (`findings: []`) — append one record to `harness codex --log` per the Learning-Capture step 4: `mode`, `verdict`, the pre-flight `applicable/dismissed/fixed` **bare** IDs, and each finding tagged `class` (matched entry ID or `novel`). Do NOT emit for challenge or consult modes — they have no verdict to record. On a non-zero exit: if stderr shows malformed JSON, fix and re-emit once; if the writer is absent or the emit otherwise fails, state it once and proceed. This is observability only — it MUST NOT block or alter the review outcome.
- If a Codex revision contradicts user requirements, skip that revision and note it
- Clean up temp files after every invocation
- Never present Codex's output as Claude's own analysis — always attribute clearly
- **ALL findings must be addressed** — fix, defer with user approval, or explain why it's a false positive. "Pre-existing" is NOT valid to skip a finding.
- After completing any review or challenge (after presenting findings and any required fixes), update the active plan file's Completion Checklist. The active plan is the unique file under `$(git rev-parse --path-format=absolute --git-common-dir | sed 's|/.git$||')/docs/plans/*.md` whose frontmatter contains `status: in-progress`. If zero or more than one plan claims `status: in-progress`, fail closed and ask the user to resolve before re-running `/second-opinion`.

  Edit the plan file: change `- [ ] Second-opinion review` to `- [x] Second-opinion review`. If you ran an adversarial challenge, add a parenthetical note: `- [x] Second-opinion review (challenge: <one-line summary>)`. The coding-team lifecycle hook reads this checkbox to enforce the gate; without the edit the pipeline will block at completion.

  If no active plan file is found (standalone `/second-opinion` invocation outside a coding-team session), skip this step — there is nothing to gate.
