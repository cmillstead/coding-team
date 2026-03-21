---
name: second-opinion
description: "Use when you want an independent second opinion from a different AI model (OpenAI Codex CLI). Three modes: review (pass/fail gate on a plan or diff), challenge (adversarial — actively tries to break your code), and consult (open-ended question to a different model). Use after /review for cross-model coverage, or during Phase 4 planning for independent plan validation. Requires Codex CLI installed: npm install -g @openai/second-opinion"
---

# /second-opinion — Cross-Model Second Opinion

Independent review from OpenAI's Codex CLI. Different model, different training, different blind spots. The overlap tells you what's definitely real. The unique findings from each are where you find the bugs neither would catch alone.

When invoked standalone:
- If the user says `/second-opinion` with no arguments: check for an active diff (`git diff main --stat`) and review it. If no diff, ask what to review.
- If the user says `/second-opinion review`: review the current diff or a specified plan file
- If the user says `/second-opinion challenge`: adversarial mode against the current diff
- If the user says `/second-opinion consult <question>`: open-ended consultation

When invoked from /coding-team pipeline: the lead specifies which mode and what to review.

---

## Prerequisite: Codex CLI

Before any mode, verify Codex CLI is available:

```bash
which codex 2>/dev/null
```

If not found: inform the user and suggest `npm install -g @openai/second-opinion`. Do NOT proceed without it.

---

## Mode 1: Review (pass/fail gate)

Independent review of a plan or diff. Codex reads the material, classifies findings by severity, and returns a verdict.

### For a diff (default)

```bash
# Generate session-scoped ID
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)

# Capture the diff
git diff main > /tmp/second-opinion-diff-${REVIEW_ID}.md

codex exec \
  -m gpt-5.3-codex \
  -s read-only \
  -o /tmp/second-opinion-review-${REVIEW_ID}.md \
  "Review the diff in /tmp/second-opinion-diff-${REVIEW_ID}.md against the codebase. Focus on:
1. Correctness — will these changes achieve the stated goals?
2. Bugs — race conditions, null propagation, off-by-ones, stale state
3. Security — trust boundaries, injection, auth bypass, secrets exposure
4. Edge cases — what inputs or states would break this?
5. Missing work — anything the diff should have changed but didn't?

Classify each finding as P1 (critical), P2 (high), or P3 (medium).
Any P1 finding = FAIL.

End with exactly: VERDICT: PASS or VERDICT: FAIL"
```

Capture the session ID from stdout for potential follow-up rounds.

### For a plan file

```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
cp <plan-file-path> /tmp/second-opinion-plan-${REVIEW_ID}.md

codex exec \
  -m gpt-5.3-codex \
  -s read-only \
  -o /tmp/second-opinion-review-${REVIEW_ID}.md \
  "Review the implementation plan in /tmp/second-opinion-plan-${REVIEW_ID}.md. Focus on:
1. Correctness — will this plan achieve the stated goals?
2. Risks — what could go wrong? Edge cases? Data loss?
3. Missing steps — is anything forgotten?
4. Alternatives — is there a simpler or better approach?
5. Security — any security concerns?

Be specific and actionable.
End with exactly: VERDICT: APPROVED or VERDICT: REVISE"
```

### Iterative revision (plan review only)

If Codex returns VERDICT: REVISE:

1. Read Codex's feedback
2. Revise the plan — address each issue. This is NOT just passing messages. Make real improvements.
3. Summarize revisions for the user
4. Re-submit to Codex using session resume:

```bash
codex exec resume ${CODEX_SESSION_ID} \
  "I've revised the plan based on your feedback. Updated plan is in /tmp/second-opinion-plan-${REVIEW_ID}.md.
Changes made: [list specific changes]
Please re-review. End with VERDICT: APPROVED or VERDICT: REVISE" 2>&1 | tail -80
```

Max 5 rounds. If `resume` fails (session expired), fall back to a fresh `codex exec` with prior context in the prompt.

### Present results

```
## Codex Review (model: gpt-5.3-codex)

**Verdict:** PASS | FAIL | APPROVED | REVISE

**Findings:**
- [P1] file:line — description
- [P2] file:line — description
- [P3] file:line — description

**Overlap with Claude review:** (if /review or audit has also run)
- [finding] — flagged by both Claude and Codex (high confidence)

**Codex-only findings:**
- [finding] — flagged only by Codex (investigate)

**Claude-only findings:**
- [finding] — flagged only by Claude (investigate)
```

The cross-model analysis is the key output. Overlapping findings are almost certainly real. Unique findings from either model are where you find the bugs neither would catch alone.

### Cleanup

```bash
rm -f /tmp/second-opinion-diff-${REVIEW_ID}.md /tmp/second-opinion-plan-${REVIEW_ID}.md /tmp/second-opinion-review-${REVIEW_ID}.md
```

---

## Mode 2: Challenge (adversarial)

Codex actively tries to break your code. Maximum reasoning effort.

```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
git diff main > /tmp/second-opinion-diff-${REVIEW_ID}.md

codex exec \
  -m gpt-5.3-codex \
  -s read-only \
  -o /tmp/second-opinion-challenge-${REVIEW_ID}.md \
  "You are an adversarial code reviewer. Your job is to BREAK this code.

Read the diff in /tmp/second-opinion-diff-${REVIEW_ID}.md and the surrounding codebase.

For each changed file, try to construct:
1. Inputs that cause crashes, panics, or unhandled exceptions
2. Sequences of operations that corrupt state
3. Race conditions under concurrent access
4. Payloads that bypass validation or escape sanitization
5. Edge cases the tests don't cover

For each attack vector you find, provide:
- The exact input or sequence
- What breaks
- Severity (P1 critical / P2 high / P3 medium)

Be specific. Show the attack, not just describe the category."
```

Present results grouped by severity. P1 findings are blockers. P2 findings must be addressed before proceeding.

---

## Mode 3: Consult (open-ended)

Ask Codex an open-ended question about the codebase. Useful for getting a different perspective on architecture, approach, or trade-offs.

```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)

codex exec \
  -m gpt-5.3-codex \
  -s read-only \
  -o /tmp/second-opinion-consult-${REVIEW_ID}.md \
  "<user's question>

Read the codebase for context. Give a specific, actionable answer."
```

Present Codex's response. If the user wants to follow up, use `codex exec resume ${CODEX_SESSION_ID}` to maintain conversation context.

---

## Pipeline Integration Points

### Phase 4: Plan review (optional second gate)

After coding-team's plan-doc-reviewer passes, offer Codex review:

```
Plan passed internal review. Want a Codex second opinion before proceeding?
```

If yes, run Mode 1 (review) against the plan file. If Codex returns REVISE, iterate up to 5 rounds. Only proceed to execution when both Claude's reviewer and Codex approve (or the user overrides).

### Phase 5: Post-audit cross-model check (optional)

After all tasks are complete and the audit loop has exited, offer Codex review of the full diff:

```
All tasks pass audit. Want a Codex second opinion on the full diff before completion?
```

If yes, run Mode 1 (review) against the diff. Cross-reference Codex findings against Claude's audit findings. Present the overlap analysis.

### Phase 5: Adversarial challenge (optional, for critical code)

For tasks tagged as security-sensitive or touching auth/payment/data-deletion:

```
This diff touches security-sensitive code. Want a Codex adversarial challenge?
```

If yes, run Mode 2 (challenge). P1 findings block completion.

### When to offer vs when to skip

Offer Codex review when:
- Plan touches 5+ files or introduces new security surface
- Diff touches auth, payment, data deletion, or encryption
- User explicitly requests it
- Audit loop found issues that were close to the refactor gate threshold (borderline findings benefit from a second perspective)

Skip when:
- Mechanical changes (rename, formatting, logging)
- Codex CLI is not installed
- User has declined Codex review in this session

Do NOT offer on every task. It adds 30-60 seconds per invocation. Match the cost to the risk.

---

## Model Selection

Default: `gpt-5.3-codex` (fast, good for standard review).

The user can override:
- `/second-opinion review o4-mini` — cheaper, faster
- `/second-opinion challenge gpt-5.4` — maximum reasoning for adversarial mode

If the default model fails or returns low-quality results, suggest upgrading to `gpt-5.4` for the retry.

---

## Cross-Model Analysis

When both Claude (via `/review` or the audit loop) and Codex have reviewed the same code, produce a cross-model analysis:

```
## Cross-Model Analysis

### Consensus (both models agree)
- [finding] — high confidence, fix these first

### Codex-only
- [finding] — different training may have caught something Claude missed. Investigate.

### Claude-only
- [finding] — Codex didn't flag this. Could be a Claude-specific concern or a Codex blind spot. Evaluate.

### Disagreements
- [topic] — Claude says X, Codex says Y. [Your assessment of who's right and why.]
```

The consensus findings are the highest-confidence issues. The model-specific findings are where the second opinion earns its value.

---

## Rules

- Codex runs in **read-only sandbox mode** — it NEVER writes files
- Always use session-scoped temp file paths (UUID prefix) to prevent conflicts between concurrent sessions
- Capture and reuse the Codex session ID for multi-round reviews — do NOT use `--last`
- If a Codex revision contradicts the user's explicit requirements, skip that revision and note it
- Clean up temp files after every invocation
- Never present Codex's output as Claude's own analysis — always attribute clearly
- **ALL findings must be addressed before proceeding** — fix, defer with user approval, or explain why it's a false positive. "Pre-existing" is NOT a valid reason to skip a finding. If the code has a bug, it has a bug regardless of when it was introduced. NEVER dismiss findings as "pre-existing, not regressions."
