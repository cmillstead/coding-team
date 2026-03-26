# Phase 3: Design Approval + Spec Review

Main Claude presents the synthesized design doc. Get explicit approval. Revise if needed.

## After User Approval

1. Write spec to `docs/plans/YYYY-MM-DD-<feature>-design.md` (always in the **main repo root**, not a worktree)
2. Dispatch spec-document-reviewer via Agent tool (model: sonnet, subagent_type: Explore). See `~/.claude/agents/ct-spec-doc-reviewer.md`)
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
> **Next:** Phase 4 will produce the implementation plan. "Proceed to Phase 4"
>
> [Only if context `used_percentage` is above 60%:]
> **Context at N%.** Clear first: `/clear` then `/coding-team continue`
>
> ---
