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

#### Verification gate (used by both revision loops)

You are the quality gate. After you apply fixes in response to Codex findings — for a plan revision OR a diff/code fix — run the project's verification command(s) via the Bash tool and confirm GREEN BEFORE you re-dispatch to Codex. This runs before EVERY re-dispatch, on every round.

1. **Discover the command(s):** find THIS repo's actual test/lint/typecheck commands from whatever build manifest or CI config it uses — e.g. `package.json` scripts, `Cargo.toml` (`cargo test`/`cargo clippy`), `go.mod` (`go test`/`go vet`), `pyproject.toml`, `Makefile`, `pom.xml`/`build.gradle`, or `.github/workflows`/`CLAUDE.md`. Do NOT assume Node/Python only. Do NOT guess a vague "run tests" — find the actual command(s) for this repo's ecosystem.
2. **Baseline first.** BEFORE applying this round's fixes — or as the first thing in this round — run the discovered command(s) and record the prior state (which tests/checks, if any, were already failing).
3. **Run them again after your fixes** with the Bash tool. Read the full output.
4. **If GREEN:** proceed to re-dispatch to Codex.
5. **If a NEW failure appeared (not in the baseline):** it is a regression YOU introduced this round. Fix it locally first, then re-run verification. Do NOT spend a Codex round on a regression you can catch locally — the next round would just rediscover what you already broke.
6. **If verification stays red ONLY due to pre-existing baseline failures (no new failures from your fixes):** do NOT loop indefinitely. STATE the failing command and which failures are pre-existing vs new, and get USER APPROVAL before re-dispatching without a green run. Do NOT silently treat a pre-existing red as license to skip verifying your own changes. If a failure looks intermittent (passes on a clean re-run with no change), treat it as flaky: re-run once to confirm, and a subsequent green needs no user approval.
7. **If the project has NO runnable test/lint/typecheck command:** STATE that explicitly (e.g., "No verification command found in the repo's build manifests or CI config — proceeding without local verification") and proceed. Do NOT silently skip, and do NOT block.

Scope note: this baseline branch governs pre-existing RED TESTS at the verification step (introduced-vs-pre-existing at the TEST level). It is DISTINCT from, and does NOT modify, the SKILL.md Rules entry "ALL findings must be addressed … 'Pre-existing' is NOT valid to skip a finding" — that rule governs CODEX FINDINGS (what Codex flags in code); this baseline branch governs VERIFICATION FAILURES (test/lint/typecheck output). They are orthogonal: a pre-existing failing test does not exempt you from fixing a Codex finding.

Known rationalizations — these are bypasses, not exemptions:
- "I'll verify at the end" — NO. The gate runs before EACH re-dispatch, not once at the end. A regression introduced in round 2 must be caught before round 3, not after round 5.
- "The fix was small / a one-liner" — NO. Size does not exempt the gate. One-line fixes cause regressions too. The gate runs every round regardless of fix size.

### Iterative revision (plan review only)

If Codex returns VERDICT: REVISE:
1. Read Codex's feedback
2. Revise the plan — address each issue with real improvements
3. **Verification gate (MANDATORY) — see "#### Verification gate (used by both revision loops)" above.** Run the project's verification command(s) and confirm GREEN (or follow the baseline branch) before re-submitting.
4. Summarize revisions for the user
5. Re-submit using session resume:

```bash
codex exec resume ${CODEX_SESSION_ID} \
  "I've revised the plan based on your feedback. Updated plan is at <plan-file-path>.
Changes made: [list specific changes]
Please re-review. End with VERDICT: APPROVED or VERDICT: REVISE" \
  2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt
```

Max 5 rounds. If `resume` fails (session expired), fall back to a fresh `codex exec` with prior context in the prompt.

### Iterative revision (diff / code-fix review)

When a diff/code review (`codex review --base main`, `codex review --uncommitted`, or a `codex exec` diff review) returns findings you intend to fix and re-review:
1. Read Codex's findings.
2. Apply fixes to the diff.
3. **Verification gate (MANDATORY) — see "#### Verification gate (used by both revision loops)" above.** Run the project's verification command(s) and confirm GREEN (or follow the baseline branch) before re-dispatching. This is the loop that most often introduces regressions — do NOT skip it.
4. Summarize the fixes you made in response to the findings (so the re-review has visibility into what changed).
5. Re-dispatch the diff review: `codex review --base main` (or `--uncommitted`), or `codex exec` with the updated `git diff`. Capture output as usual.

Max 5 rounds, consistent with the plan-revision loop. If findings persist after the cap, present remaining findings to the user rather than looping further.

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

## Mode 2: Challenge (adversarial)

Codex actively tries to break your code via `codex exec` with an adversarial prompt. Tests for: crash inputs, state corruption sequences, race conditions, validation bypasses, untested edge cases. Use the adversarial prompt template under "Challenge: adversarial review" above.

Present results grouped by severity. P1 findings are blockers. P2 must be addressed before proceeding.

### Cleanup
```bash
rm -f /tmp/second-opinion-challenge-${REVIEW_ID}.txt
```

## Mode 3: Consult (open-ended)

Ask Codex an open-ended question about the codebase via `codex exec`. Use the prompt template under "Consult: open-ended question" above. For follow-ups, use `codex exec resume ${CODEX_SESSION_ID}` to maintain conversation context.

### Cleanup
```bash
rm -f /tmp/second-opinion-consult-${REVIEW_ID}.txt
```

## Cross-Model Analysis

When both Claude and Codex have reviewed the same code, produce a cross-model analysis showing consensus findings, Codex-only findings, Claude-only findings, and disagreements.

### Cross-Model Analysis Template

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

## Post-Review: Learning Capture

After every Codex review that produces findings (any mode), before cleanup:

1. Read `skills/second-opinion/codex-learnings.d/_header.md` and every entry file in `codex-learnings.d/` (glob, exclude `_header.md`) to know the live IDs.
2. For each finding Codex raised: does it match an existing pattern (any existing P## / C## entry)?
   - **Yes**: no action — pre-flight should have caught it. If it didn't, check why pre-flight missed it and tighten the existing entry file's description.
   - **No**: is this a one-off or a recurring class of mistake?
     - **One-off** (project-specific logic error): skip
     - **Recurring** (would apply to other plans/code): write a NEW FILE in `codex-learnings.d/` — NEVER edit a shared file. Filename: `<YYYYMMDD-HHMMSS>-<rand4>-<slug>.md` where the timestamp is the current UTC datetime and `<rand4>` is 4 random hex characters (e.g. `20260619-143022-a3f1-path-equality-mismatch.md`). The `<rand4>` component makes same-second concurrent writes collision-safe: `python3 -c "import secrets; print(secrets.token_hex(2))"`. Never reuse or hand-pick a sequential ID — the filename stem IS the entry's canonical ID. The file contains: original P##/C## family label as the heading, the `@tags:` token (category + `provable`/`reasoning-shape` + scope), the pattern description, and the "Check before dispatch" body — born tagged in the same file creation (see the capture footer in `_header.md`). If no existing category fits, add the new category to the enum and battery in `_header.md` in the same session.
3. Report: `Learning capture: added C15 (<name>)` or `Learning capture: no new patterns`

## Model Selection

Default: Codex CLI default model (no `-m` flag). User can override with `-m MODEL`:
- `/second-opinion review o4-mini` — cheaper, faster
- `/second-opinion challenge o3` — maximum reasoning for adversarial mode

If default returns low-quality results, suggest retrying with a stronger model.
