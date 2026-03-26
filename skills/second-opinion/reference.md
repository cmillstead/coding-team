# Second Opinion — Reference

## Codex Command Examples

### Review: diff against main
```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
codex review --base main 2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt
```

Note: `codex review` runs an opinionated review automatically — custom instructions cannot be passed with `--base`. For custom-prompted reviews, use Mode 3 (consult) with an explicit `git diff` command.

### Review: uncommitted changes
```bash
codex review --uncommitted 2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt
```

### Review: plan file
```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
codex exec \
  "Review the implementation plan at <plan-file-path>. Focus on:
1. Correctness — will this plan achieve the stated goals?
2. Risks — what could go wrong? Edge cases? Data loss?
3. Missing steps — is anything forgotten?
4. Alternatives — is there a simpler or better approach?
5. Security — any security concerns?

Be specific and actionable.
End with exactly: VERDICT: APPROVED or VERDICT: REVISE" \
  2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt
```

### Iterative revision (plan review only)

If Codex returns VERDICT: REVISE:
1. Read Codex's feedback
2. Revise the plan — address each issue with real improvements
3. Summarize revisions for the user
4. Re-submit using session resume:

```bash
codex exec resume ${CODEX_SESSION_ID} \
  "I've revised the plan based on your feedback. Updated plan is at <plan-file-path>.
Changes made: [list specific changes]
Please re-review. End with VERDICT: APPROVED or VERDICT: REVISE" \
  2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt
```

Max 5 rounds. If `resume` fails (session expired), fall back to a fresh `codex exec` with prior context in the prompt.

### Challenge: adversarial review
```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
codex exec \
  "You are an adversarial code reviewer. Your job is to BREAK this code.

Run 'git diff main' to see the changes, then read the surrounding codebase for context.

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

Be specific. Show the attack, not just describe the category." \
  2>&1 | tee /tmp/second-opinion-challenge-${REVIEW_ID}.txt
```

### Consult: open-ended question
```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
codex exec \
  "<user's question>

Read the codebase for context. Give a specific, actionable answer." \
  2>&1 | tee /tmp/second-opinion-consult-${REVIEW_ID}.txt
```

For follow-ups: `codex exec resume ${CODEX_SESSION_ID} "FOLLOW-UP QUESTION"`

## Cross-Model Analysis Template

When both Claude and Codex have reviewed the same code:

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

## Pipeline Integration Points

### Phase 4: Plan review (optional second gate)
After coding-team's plan-doc-reviewer passes, offer Codex review. If Codex returns REVISE, iterate up to 5 rounds. Only proceed when both Claude's reviewer and Codex approve (or user overrides).

### Phase 5: Post-audit cross-model check (optional)
After all tasks pass audit, offer Codex review of the full diff. Cross-reference findings against Claude's audit.

### Phase 5: Adversarial challenge (optional, for critical code)
For tasks touching auth/payment/data-deletion, offer Codex adversarial challenge. P1 findings block completion.

### When to offer vs skip
Offer when: plan touches 5+ files or new security surface, diff touches auth/payment/data-deletion/encryption, user requests it, or borderline audit findings.
Skip when: mechanical changes, Codex CLI not installed, or user declined in this session. Do NOT offer on every task — it adds 30-60s per invocation.
