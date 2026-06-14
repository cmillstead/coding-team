# Task Weight Ladder

Loaded by the orchestrator from `SKILL.md` Step 0 (task routing) and referenced by every pipeline gate to classify task weight. This file is the SINGLE source of truth for (a) how a task's tier is computed and (b) exactly which gates run per tier. No other file invents its own risk criteria or gate table.

## Identity + one-classifier rule

You are the task-weight classifier. Classify every task into exactly one tier BEFORE routing. Tier determines which gates run — gates are tier-conditional, not unconditional.

**Risk is defined in exactly ONE place: this file's semantic risk-signal checklist.** Individual gates NEVER invent their own risk criteria and NEVER re-derive risk with ad-hoc local rules — they consume the tier. That single checklist is applied at exactly TWO defined points: (1) at PLANNING (size + risk → planned tier), and (2) ONCE MORE at the shared post-exec/Phase-6 RATCHET, where the SAME checklist is re-applied to the ACTUAL diff (→ effective tier = max(planned, actual), promote-only). The ratchet is the SAME classifier applied a second time to reality — NOT a gate making up its own rules. "Gates never re-derive risk" and "the shared ratchet re-applies this checklist to the diff" are consistent: one classifier, two application points, zero gate-local risk rules.

## Size-tier table (size dimension only)

| Size-tier | Quantified definition (size only) |
|---|---|
| **Trivial** | 1 file, ≤20 lines, fully specified, no architectural decision |
| **Small** | ≤3 files, no new deps/schema/security surface |
| **Medium** | 4-10 files |
| **Large** | 10+ files OR architectural change |

## Risk signals — these force Medium MINIMUM regardless of size

**Tier = max(size-tier, risk-tier).** Risk signals OVERRIDE size. A 1-file/≤20-line change carrying ANY risk signal below is **never Trivial and never Small** — it is **Medium minimum** (Large if it is also an architectural change). This is a quantified rule stated at EQUAL force to the size thresholds, not a "may/consider".

**Judge by what the change DOES, not what the file is NAMED.** The filename patterns below are HINTS to help you spot a risk class — they are NOT the definition. A 15-line authz tweak in `utils.py`, a crypto change in `handler.ts`, or a permission check in `middleware.go` is Medium minimum even though the filename matches no pattern. Classify by effect.

**This risk set is a deliberate SUPERSET of every high-stakes category the existing harness already special-cases** (`phases/planning.md:27` "Auth, payment, encryption, or data-deletion code paths"; `phases/planning-next-steps.md:11` `auth, payment, encryption, session, token, CORS, CSP`; `phases/execution.md:105` `auth|payment|encrypt|session|token|cors|csp|secret|credential|permission`; `phases/post-execution-review.md:10-13` security + instruction-file signals; `~/.claude/CLAUDE.md` "Ask First" deps/API + "high-stakes (payments, permissions, data deletion)" + scan-* triggers; `hooks/write-guard.py` migrations/secrets/instruction files). No category the harness recognizes is weaker under the ladder.

A task has a risk signal if it DOES any of:
- **Security / trust-boundary effect:** alters authentication, authorization, session or token handling, cryptography/encryption, secret/credential handling, a permission/access check, CORS/CSP/CSRF policy, or an input-trust boundary (parsing/validating/deserializing untrusted input). *Filename hints (not the definition):* `auth, session, token, crypto, encrypt, permission, secret, credential, csrf, cors, csp, middleware, guard, validate`.
- **Payment / billing / financial effect:** alters payment capture, billing, charges, refunds, invoicing, pricing, or any money-moving / financial-record path — in ANY file, regardless of name. (Harness already treats `payment` as security-sensitive: `planning.md:27`, `planning-next-steps.md:11`, `execution.md:105`, CLAUDE.md high-stakes.)
- **Data-deletion / destructive-data effect:** performs a bulk delete, `DROP`/`TRUNCATE`, irreversible mutation, cascade delete, or any destructive / non-recoverable data path — regardless of file. (Harness high-stakes: `planning.md:27` "data-deletion code paths"; CLAUDE.md "data deletion".)
- **Public-contract effect:** changes any exported/public signature, API route or endpoint, CLI flag, wire/JSON/protobuf format, or other consumer-visible contract — in ANY file, regardless of name. (CLAUDE.md "Ask First: Changing public API contracts".)
- **Schema/data effect:** any DDL, schema, migration, or index change — regardless of directory. *Hints:* `migrations/, schema, alembic/, prisma/`.
- **Dependency effect:** any dependency add or version bump — regardless of manifest name. *Hints:* `package.json, pyproject.toml, Cargo.toml, go.mod, Gemfile, requirements.txt`.
- **Behavioral-instruction-file edit:** ANY edit to `phases/*.md`, `SKILL.md`, `agents/*.md`, `prompts/*.md`, `CLAUDE.md`, `hooks/*`. (Same high-impact surface `hooks/write-guard.py:43-57` always-delegates and `phases/post-execution-review.md:10-13` always flags. A 1-line instruction-file change can cascade across every pipeline run.)

**When unsure whether a change has a risk effect, treat it as a risk signal (fail UP).** The filename hints exist to catch the obvious cases cheaply; they never EXCLUDE a semantically-risky change in a generically-named file.

**Consequence for this very repo:** coding-team IS instruction files, so every coding-team-on-itself task is Medium+ and KEEPS full review + verification. The fast lane (Trivial/Small) is ONLY for benign source / test / doc changes in TARGET repos, never for edits to the harness itself.

## Gate matrix — single source of truth (each gate task references this, never re-defines it)

| Gate | Trivial | Small | Medium | Large |
|---|---|---|---|---|
| Phase 1 dialogue (full Q→approach→approval) | SKIP | SKIP | RUN | RUN |
| Phase 2 design team | SKIP | SKIP (inline design note) | RUN | RUN |
| Phase 3 spec-doc reviewer | SKIP | SKIP | RUN | RUN |
| Plan Codex `review` gate | SKIP | SKIP | RUN (required) | RUN (required) |
| Plan reviewer tiebreaker (iter 2+) | SKIP | SKIP | RUN | RUN |
| QA reviewer (`ct-qa-reviewer`) | SKIP | RUN | RUN | RUN |
| Per-task verification subagent | SKIP | RUN | RUN | RUN |
| Post-exec Codex `review` | SKIP | RUN (required) | RUN (required) | RUN (required) |
| Doc-drift scan | SKIP | RUN | RUN | RUN |
| Full-suite re-runs (Phase 6 entry + pre-push) | 1 run total | standard | standard | standard |
| Wiki article | SKIP | SKIP unless patterns | offer | offer |
| Decision-log prompt | SKIP | offer | offer | offer |
| Completion summary file | SKIP | RUN | RUN | RUN |
| Codex `challenge` | offered | offered | offered | offered |

Reading rule: **Trivial** skips ALL discretionary gates (single haiku task, one test+lint run only). **Small** additionally KEEPS the QA reviewer, the per-task verification subagent, AND the post-exec Codex `review` — it only sheds the design team, the plan Codex gate, and wiki/decision-log ceremony. The Trivial-vs-Small difference is exactly: QA reviewer + verification subagent + post-exec review + doc-drift + completion summary all RUN at Small and SKIP at Trivial. Every gate task in this plan (Tasks 9, 9a, 11, 12, 13, 14, 17, 18, 19) must encode precisely the column values above — no task invents a different fast lane. The END-OF-EXECUTION gates (QA, doc-drift, verification sweep, post-exec review, Phase-6) all read the EFFECTIVE tier from the single recompute (Task 9a); only the pre-diff gates (dialogue, design team, plan Codex, spec reviewer) read the planned tier.

## Gate rule (equal-force framing)

Each gate is written `if tier in {RUN-columns}: run`. The skip path is stated at EQUAL force to the run path — a Trivial task MUST skip a gate with the same certainty a Large task MUST run it. This is not `may`/`consider`; it is a quantified rule keyed to the matrix above.

## Scoped-skip clause

These skips are SCOPED to the quantified tiers + risk signals above. An UNSCOPED skip — "skip because it's simple/trivial/small" with no tier — remains forbidden (`named-rationalizations.md`). Tier-scoped right-sizing is REQUIRED and correct; unscoped bypass is still a violation.

## Canonical Codex principle (stated ONCE here)

**Codex `challenge` is always OFFERED, never REQUIRED.** `review` is tier-gated per the matrix; `challenge` is only ever offered, at every tier. Other files reference this line; they do not restate the rule.

## Classification procedure

1. Compute size-tier from file/line count.
2. Scan for risk signals (SEMANTIC — by effect, not filename).
3. If any risk signal present, set risk-tier = Medium (or Large if architectural).
4. **Tier = max(size-tier, risk-tier)** — fail UP, never down.

## The planned tier is a FLOOR, not a final verdict — recompute ONCE at end-of-execution

The tier you assign at planning is a FLOOR. A task PLANNED as Trivial/Small can GROW during implementation — more files, more lines, or a risk signal that only emerged in the code. Applying the low planned tier to a grown diff would skip gates the FINAL diff needs.

**Recompute the effective tier exactly ONCE, as the FIRST action of the end-of-execution gate sequence** — after the last implementer task and BEFORE the earliest tier-gated exit gate (the QA reviewer), so EVERY end gate evaluates the same up-to-date tier. (The earliest tier-gated exit gate is the QA reviewer at `phases/execution.md:151`, which runs before doc-drift, the verification sweep, post-exec Codex review, and the Phase-6 gates. If the recompute were deferred to post-exec, QA and doc-drift would wrongly use the stale planned tier.) Re-apply THIS file's classifier to the ACTUAL diff: SIZE input = actual file/line counts; RISK input = the SAME SEMANTIC RISK-SIGNAL CHECKLIST above (judge by what the diff DOES). Then:

  **effective tier = max(planned tier, actual-diff tier)**

Tier ratchets UP only — NEVER apply a planned-lower tier to a diff that grew, and NEVER lower a tier (a planned risk stays). **This single recompute is CARRIED into every end-of-execution gate — QA reviewer, doc-drift scan, per-task verification sweep, post-exec Codex review, and the Phase-6 gates. No end gate reads the planned tier directly; they all read this one effective tier.** One recompute, many consumers.

This is cheap and tier-appropriate, and it uses ONE source of truth: the planning-time classifier and this recompute apply the IDENTICAL semantic checklist, so a change can never be classified one way at planning and another at recompute.
- **SIZE input:** `git diff $(git merge-base HEAD main) --name-only | wc -l` for the file count, plus the changed-line count.
- **RISK input:** re-run the full SEMANTIC risk-signal checklist (security/trust-boundary, payment/billing/financial, data-deletion/destructive, public-contract, schema/data, dependency, instruction-file) against what the diff actually DOES. **NOT a grep** — filename patterns are HINTS only; an authz or public-contract change in `utils.py` must still be detected by reading the diff's effect. Recomputing tier is counting + this semantic checklist, NOT always running the heavy Codex gate. Trivial diffs still skip; grown or newly-risky diffs get promoted and gated.

## Return instruction

After classifying, return to `SKILL.md` Step 3 (Route) with the planned tier (the FLOOR). Carry it through every pre-diff phase. At end-of-execution, recompute the effective tier = max(planned, actual-diff) ONCE — as the FIRST action of the exit-gate sequence, before the earliest tier-gated gate (the QA reviewer) — and have ALL end-of-execution gates (QA, doc-drift, verification sweep, post-exec review, Phase-6) evaluate the matrix against that one EFFECTIVE tier.
