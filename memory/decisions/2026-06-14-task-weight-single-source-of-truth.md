---
name: task-weight tier ladder as single gating source of truth
description: phases/task-weight.md becomes the ONE place tier is computed and the ONE gate matrix every phase file consumes — no gate re-derives risk criteria locally
type: project
---

## Context
`docs/weight-asymmetry-audit-2026-06-14.md` found 36 process-weight findings: coding-team applied roughly the same ceremony (design team, spec review, Codex gates, QA reviewer, post-exec review, wiki, decision log) to a 1-line typo fix and a 30-file architectural change. Multiple phase files (`planning.md`, `planning-next-steps.md`, `execution.md`, `post-execution-review.md`) each had their own ad-hoc risk criteria (auth/payment/encryption keyword lists) that could drift from each other.

## Decision
`docs/plans/2026-06-14-coding-team-fastlane.md` (Batch 2, Tasks 8-21, commits on branch `coding-team-weight-ladder-batch2`, stacked on PR #73) introduced `phases/task-weight.md` as the SINGLE classifier and SINGLE gate matrix:

- **Tier = max(size-tier, risk-tier).** Size: Trivial (1 file, ≤20 lines) / Small (≤3 files) / Medium (4-10 files) / Large (10+ or architectural). Risk signals (security/trust-boundary, payment/billing, data-deletion, public-contract, schema/data, dependency, behavioral-instruction-file edit) force Medium MINIMUM regardless of size, judged by what the change DOES not what the file is named ("fail UP" when unsure).
- **Gate matrix** (one table) says exactly which of: Phase 1 dialogue, Phase 2 design team, Phase 3 spec-doc reviewer, plan Codex review, QA reviewer, per-task verification, post-exec Codex review, doc-drift scan, wiki article, decision-log prompt, completion summary — RUN vs SKIP at each tier. No other file may invent its own gate condition.
- **Single end-of-execution recompute:** tier is computed once at planning (the FLOOR), then recomputed exactly ONCE as the first action of the end-of-execution gate sequence (before the QA reviewer), re-applying the SAME semantic checklist to the actual diff. `effective tier = max(planned, actual-diff)` — ratchets up only, never down. This single recompute is carried into every end gate (QA, doc-drift, verification sweep, post-exec review, Phase 6) — no end gate reads the planned tier directly.
- **Consequence for coding-team-on-itself:** every edit to coding-team's own instruction files is Medium+ by the behavioral-instruction-file risk signal — the fast lane never applies to harness self-edits, only to benign source/test/doc changes in target repos.

Passed 11 Codex (`/second-opinion review`) rounds before the user directed proceeding to execution without a final formal PASS (iteration 12 addressed the last real defect: the single end-of-execution recompute point). A post-exec Codex review after Batch 2 landed caught one more temporal bug (per-task verification gate referenced the not-yet-computed effective tier) — fixed same day (`bf301da`).

## Alternatives Considered
- **Per-phase local risk criteria** (status quo before this decision) — rejected: risk keyword lists had already drifted across `planning.md`, `planning-next-steps.md`, `execution.md` before this fix; a second classifier inevitably diverges from the first.
- **Recompute tier at every phase boundary** — rejected: cheap but redundant: since tier only ratchets up and the risk checklist is identical, one recompute at the earliest point all end-gates need it is sufficient and avoids repeated re-classification of the same diff mid-execution.

## Constraints
- Individual gate tasks (SKILL.md, execution.md, completion.md, post-execution-review.md, planning-next-steps.md, audit-loop.md, doc-drift-scan.md) must reference `phases/task-weight.md`, never restate the size/risk table locally except for the "equal-force" gate phrasing pattern.
- The recompute point is fixed at "before the QA reviewer" (`phases/execution.md`) — moving it later (e.g. to post-exec) was tried and found wrong by Codex (QA/doc-drift would read the stale planned tier).

## Consequences
- Trivial tasks: single haiku task, one test+lint run, no design team, no QA reviewer, no wiki, no decision log.
- Any task that touches an instruction file, auth/payment/crypto path, schema, public contract, or a dependency manifest is Medium+ regardless of line count — full review stack applies.
- Future gate additions MUST add a column to `phases/task-weight.md`'s matrix rather than invent a local skip condition — this is the DRY invariant the fastlane audit was built to establish and Codex verified mechanically (grep found the ladder table lives only in task-weight.md).
