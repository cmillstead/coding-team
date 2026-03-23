# Planning Next Steps

After the plan passes review and is saved:

1. Evaluate risk signals against the plan:

| Signal | Detection |
|---|---|
| Plan touches 5+ files | Count files in task list `**Files:**` sections |
| Plan has opus-tier tasks | Any task with `**Model:** opus` |
| Plan introduces new security surface | Tasks touch auth, payment, encryption, session, token, CORS, or CSP files |
| Plan modifies CC instruction files | Tasks touch `phases/*.md`, `skills/*/SKILL.md`, `prompts/*.md`, `CLAUDE.md`, `SKILL.md` |
| Plan includes database migrations | Tasks create or alter schema, migrations, or indexes |
| User previously requested Codex review | User said "codex", "second opinion", or "cross-model" in this session |

2. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.

3. **If ANY risk signal is true AND Codex is available**, print this VERBATIM (substitute actual values), then STOP — do not print anything after this block. Your next message depends on the user's answer:

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> This plan [touches N files / modifies security surface / has opus-tier tasks / etc.].
>
> Run `/second-opinion review` for an independent second opinion on the plan? (Y/n)
>
> ---

   - User says yes: run `/second-opinion review` against the plan file. After Codex review completes, continue with step 4.
   - User says no or sends a different message: continue with step 4.

4. **If no risk signals fire OR Codex is not available OR Codex review is done**, print this VERBATIM (substitute actual values):

> ---
>
> **Plan saved to `docs/plans/<actual-path>`.**
>
> **Next:** Phase 5 execution. "Proceed to Phase 5"
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

**User override:** If the user has said "never ask about second opinion" or "skip second-opinion gates" in this session, skip second-opinion in planning for the rest of the session.
