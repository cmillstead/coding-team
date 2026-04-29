---
name: second-opinion
description: Get an independent review from OpenAI Codex CLI (review, challenge, or consult mode)
argument-hint: "[review|challenge|consult <question>] [model]"
---

# /second-opinion — Cross-Model Second Opinion

Independent review from OpenAI's Codex CLI. Different model, different blind spots. Overlapping findings are high-confidence. Unique findings from each model are where the second opinion earns its value.

When invoked:
- No arguments: check for active diff (`git diff main --stat`) and review it. If no diff, ask what to review.
- `review`: review current diff or specified plan file
- `challenge`: adversarial mode against current diff
- `consult <question>`: open-ended consultation

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
- After completing any review or challenge (after presenting findings and any required fixes), update the active plan file's Completion Checklist. The active plan is the unique file under `$(git rev-parse --path-format=absolute --git-common-dir | sed 's|/.git$||')/docs/plans/*.md` whose frontmatter contains `status: in-progress`. If zero or more than one plan claims `status: in-progress`, fail closed and ask the user to resolve before re-running `/second-opinion`. Edit the plan: change `- [ ] Second-opinion review` to `- [x] Second-opinion review`. If you ran an adversarial challenge, add a note: `- [x] Second-opinion review (challenge: <one-line summary>)`. The coding-team lifecycle hook reads this checkbox to enforce the gate; without the edit the pipeline will block at completion. If no active plan file is found (standalone `/second-opinion` outside a coding-team session), skip this step.
