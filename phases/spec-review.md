# Phase 3: Spec Review

The design doc was already approved in Phase 2 (`phases/design-team.md`). This phase WRITES that
approved design up as a spec and reviews it — it does not re-approve it. Approving the same design a
third time (approach in Phase 1, design doc in Phase 2, spec here) elicits no new preference and
stalls the pipeline.

## Steps

1. Write spec to `docs/plans/YYYY-MM-DD-<feature>-design.md` (always in the **main repo root**, not a worktree)
2. **Seam ownership** — for any two-agent split, the spec MUST name which agent OWNS the interface/seam between them (the shared file, data contract, or API boundary). An unowned agent↔agent seam fails every run even when both halves are individually correct. If the seam is unnamed, fix the spec before continuing.
3. **Spec-doc reviewer tier gate (PLANNED tier — this phase runs pre-diff, before any
   implementation exists, so no effective-tier recompute is available yet):**
   - Trivial/Small SKIP the spec-doc reviewer. Small inlines a design note instead of a
     heavyweight spec; no separate reviewer dispatch is needed.
   - Medium/Large RUN it: dispatch spec-document-reviewer via Agent tool
     (subagent_type: Explore). See `~/.claude/agents/ct-spec-doc-reviewer.md`. Gate matrix:
     `phases/task-weight.md`.
4. If Issues Found: fix, re-dispatch, repeat (max 3 iterations, then surface to user)
5. If Approved: continue to the Second-Opinion Gate below.

## Second-Opinion Gate (before Phase 4)

1. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.
2. Check if the spec introduces new architecture: new services, new data flows, new external integrations, or new database schemas.
3. **If Codex is available AND new architecture was detected in step 2**, RUN it — do not ask. The
   architecture signal is the trigger; catching issues here is cheaper than after the plan is
   written, and that tradeoff is already decided. Print one line naming what triggered it:

> This spec introduces new [services/data flows/integrations] — running `/second-opinion consult` before planning.

   Then run `/second-opinion consult "Review this design spec for architectural risks, missing edge cases, and unstated assumptions: <spec-file-path>"`. Triage any findings into the spec, then continue.

If Codex is unavailable, or no new architecture was detected, skip silently and continue.

---

## Next Steps

After the spec is written and reviewed, print this block VERBATIM (substitute the actual date and feature name for the path):

> ---
>
> **Spec written and reviewed — saved to `docs/plans/<actual-path>`.**
>
> **Continuing to Phase 4** — producing the implementation plan.
>
> [Only if context `used_percentage` is above 60%:]
> **Context at N%.** Clear first: `/clear` then `/coding-team continue`
>
> ---

**Final step — enter Phase 4.** The design approval that authorizes this work was given in Phase 2; this phase adds no gate of its own. Read `phases/planning.md` now and execute its first step. Do not re-summarize the spec and do not wait for a go-ahead phrase. **If the tier gate at the top of this file routed this task past the next phase, that routing wins** — enter the phase it named instead. If the user spontaneously asks for spec changes, stay in this phase and revise — but do not solicit that request.
