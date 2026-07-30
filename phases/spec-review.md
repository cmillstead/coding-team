# Phase 3: Design Approval + Spec Review

Main Claude presents the synthesized design doc. Get explicit approval. Revise if needed.

## After User Approval

1. Write spec to `docs/plans/YYYY-MM-DD-<feature>-design.md` (always in the **main repo root**, not a worktree)
2. **Spec-doc reviewer tier gate (PLANNED tier — this phase runs pre-diff, before any
   implementation exists, so no effective-tier recompute is available yet):**
   - Trivial/Small SKIP the spec-doc reviewer. Small inlines a design note instead of a
     heavyweight spec; no separate reviewer dispatch is needed.
   - Medium/Large RUN it: dispatch spec-document-reviewer via Agent tool (model: sonnet,
     subagent_type: Explore). See `~/.claude/agents/ct-spec-doc-reviewer.md`. Gate matrix:
     `phases/task-weight.md`.
3. If Issues Found: fix, re-dispatch, repeat (max 3 iterations, then surface to user)
4. If Approved: present spec to user for final review before proceeding

## Second-Opinion Gate (after spec approval, before Phase 4)

1. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.
2. Check if the spec introduces new architecture: new services, new data flows, new external integrations, or new database schemas.
3. **If Codex is available**, ALWAYS offer — architecture signals determine the framing, not whether to ask:

> [If new architecture detected: "This spec introduces new [services/data flows/integrations]. "]
> [If no new architecture: ""]
> `/second-opinion consult` on the spec before planning? Catching issues here is cheaper than after the plan is written. (Y/n)

   - User says yes: run `/second-opinion consult "Review this design spec for architectural risks, missing edge cases, and unstated assumptions: <spec-file-path>"`. After review, continue to step 5.
   - User says no: continue to step 5.

If Codex is not available, skip silently.

5. Only proceed to Phase 4 after user confirms the written spec

---

## Next Steps

After the user confirms the spec, print this block VERBATIM (substitute the actual date and feature name for the path):

> ---
>
> **Spec confirmed and saved to `docs/plans/<actual-path>`.**
>
> **Continuing to Phase 4** — producing the implementation plan.
>
> [Only if context `used_percentage` is above 60%:]
> **Context at N%.** Clear first: `/clear` then `/coding-team continue`
>
> ---

**Final step — enter Phase 4.** The required approval was already given above — that is what triggered this block; it is not a second gate. Read `phases/planning.md` now and execute its first step. Do not re-summarize what was just approved and do not wait for a go-ahead phrase. **If the tier gate at the top of this file routed this task past the next phase, that routing wins** — enter the phase it named instead. If the user asks for spec changes, stay in this phase and revise until the written spec is confirmed — do not enter Phase 4 early, and once it is confirmed do not stop to ask again.
