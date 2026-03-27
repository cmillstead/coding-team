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

## Mode 1: Review (pass/fail gate)

Independent review of a plan or diff. Use `codex review --base main` for diffs, `codex review --uncommitted` for unstaged changes, or `codex exec` for plan files (see reference.md for exact commands).

Always capture output: `2>&1 | tee /tmp/second-opinion-review-${REVIEW_ID}.txt`

For plan reviews: if Codex returns VERDICT: REVISE, iterate up to 5 rounds using `codex exec resume`. Address each issue with real improvements between rounds.

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

## Rules

- `codex review` is read-only. `codex exec` in challenge/consult has full access but is used only for analysis.
- Always use session-scoped temp file paths (UUID prefix) to prevent conflicts
- Capture output with `2>&1 | tee /tmp/second-opinion-*.txt` — there is no `-o` flag
- Reuse Codex session ID for multi-round reviews via `codex exec resume SESSION_ID`
- If a Codex revision contradicts user requirements, skip that revision and note it
- Clean up temp files after every invocation
- Never present Codex's output as Claude's own analysis — always attribute clearly
- **ALL findings must be addressed** — fix, defer with user approval, or explain why it's a false positive. "Pre-existing" is NOT valid to skip a finding.
- After completing any review or challenge (after presenting results), write the completion marker: `touch /tmp/second-opinion-completed`. This marker is checked by `/release` to enforce the second-opinion gate within the pipeline. The marker is cleaned up automatically by the coding-team lifecycle hook when the pipeline ends.
