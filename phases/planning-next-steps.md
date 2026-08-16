# Planning Next Steps

After the plan passes review and is saved:

1. Evaluate risk signals against the plan:

| Signal | Detection |
|---|---|
| Plan touches 5+ files | Count files in task list `**Files:**` sections |
| Plan introduces new security surface | Tasks touch auth, payment, encryption, session, token, CORS, or CSP files |
| Plan modifies CC instruction files | Tasks touch `phases/*.md`, `agents/*.md`, `skills/*/SKILL.md`, `CLAUDE.md`, `SKILL.md` |
| Plan includes database migrations | Tasks create or alter schema, migrations, or indexes |
| User previously requested Codex review | User said "codex", "second opinion", or "cross-model" in this session |

2. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.

3. **If Codex is available AND the planned tier is ≥ Medium** (per `phases/task-weight.md`): run the plan second-opinion (REQUIRED). If the planned tier is Trivial or Small: SKIP the plan second-opinion — proceed directly to step 4. Risk signals determine the framing of the print, not whether to run the gate. Print this VERBATIM (substitute actual values), then run the gate:

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> [If risk signals fired: "This plan [touches N files / modifies security surface / etc.]."]
>
> Running `/second-opinion review` on the plan — required at tier ≥ Medium.
>
> ---

   - Run `/second-opinion review` against the plan file. After Codex review completes, continue with step 4.
   - If the user has overridden the gate for this session (see the override below), skip it and continue with step 4.

4. **If Codex is not available OR second-opinion review is done**, print this VERBATIM (substitute actual values):

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> **Continuing to Phase 5** — execution.
>
> **Recommended before execution:**
> - `/worktree` — set up an isolated workspace (offered automatically)
>
> **Context check:** Check `used_percentage` from the context window. Only suggest clearing if above 60%. The plan is on disk — clearing is safe but not always necessary.
>
> **If above 60%:** "Context is at N%. Recommend clearing before execution: `/clear` then `/coding-team continue`"
> **If below 60%:** Do NOT suggest clearing. Just proceed.
>
> **During execution:** If you hit a bug that requires investigation, `/scope-lock` will lock edits to the affected directory so debugging can't accidentally change unrelated code. `/debug` auto-suggests this.
>
> ---

**Named rationalizations (compliance triggers) and user override — equal-force rules:**
- "The user wants to move fast" — speed does not exempt the gate. The question takes 5 seconds to ask. Skipping it risks hours of rework.
- "The plan was already reviewed by the plan reviewer" — plan reviewer checks internal consistency. Second-opinion checks cross-model blind spots. These are different quality dimensions.
- "It's a small/trivial plan" — Trivial and Small plans skip the plan second-opinion (per `phases/task-weight.md` gate matrix). Medium+ plans run it. Tier-scoped skips are correct; unscoped "skip because small" is still a violation.
- **User override (equal force):** If the user has said "never ask about second opinion" or "skip second-opinion gates" in this session, skip second-opinion in planning for the rest of the session. A valid user override is as authoritative as a tier-skip — honor it without resistance.

**Final step — enter Phase 5.** Read `phases/execution.md` now and execute its first step. Do not stop to summarize and do not wait for a go-ahead phrase from the user — the block above is a status print, not a question, and a passing gate verdict is not a completion.
