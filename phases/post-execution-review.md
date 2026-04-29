# Post-Execution Review

> Loaded by the orchestrator from `phases/execution.md` after all Phase 5 tasks are complete. After following these instructions, proceed to Phase 6 (read `phases/completion.md`).

After all tasks are executed and verified:

1. Evaluate risk signals against the completed diff. Run these commands:
   a. Count changed files: `git diff $(git merge-base HEAD main) --name-only | wc -l`
   b. If count is 5+, gate fires.
   c. Check for security-sensitive files: `git diff $(git merge-base HEAD main) --name-only | grep -iE "auth|payment|encrypt|session|token|cors|csp"`
   d. If any output, gate fires.
   e. Check for CC instruction files: `git diff $(git merge-base HEAD main) --name-only | grep -iE "phases/|agents/|skills/|prompts/|CLAUDE.md|SKILL.md"`
   f. If any output, gate fires.

2. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.

3. **If Codex is available**, ALWAYS offer second opinion — risk signals determine the framing, not whether to ask. Print this VERBATIM (substitute actual values), then STOP — do not print anything after this block. Your next message depends on the user's answer:

> ---
>
> **All tasks executed and verified.**
>
> [If risk signals fired: "This diff [changes N files / touches security-sensitive code / modifies CC instructions / etc.]."]
> [If no risk signals: "Clean diff — N files changed."]
>
> Run Codex on the full diff? Options: **review** / **challenge** (adversarial — recommended for security-sensitive changes) / **both** / **skip**
>
> ---

   - User says "review": run `/second-opinion review` against the diff. Then continue with step 3a.
   - User says "challenge": run `/second-opinion challenge` against the diff. Then continue with step 3a.
   - User says "both": run `/second-opinion review` first, then `/second-opinion challenge`. Then continue with step 3a.
   - User says "skip" or sends a different message: edit the active plan file's Completion Checklist — change `- [ ] Second-opinion review` to `- [x] Second-opinion review (skip: <one-sentence reason from the user>)`. If no reason was given, use `(skip: user-declined)`. The lifecycle hook accepts either `[x]` or any line containing `skip:`. Then continue with step 4.

   3a. **After Codex review completes — findings gate.** If Codex returned ANY P1 or P2 findings:
   - List every finding with severity
   - Do NOT proceed to Phase 6. Do NOT dismiss findings as "pre-existing" or "not regressions"
   - Every finding must be: fixed (dispatch implementer), deferred (with explicit user approval), or explained as false positive (with reasoning)
   - After fixes, re-run Codex to verify. Only proceed when findings are resolved.
   - If no P1/P2 findings (only P3 or clean): continue with step 4.

   **Note:** `/second-opinion` edits the active plan file's Completion Checklist on completion (changes `- [ ] Second-opinion review` to `- [x]`). `/release` checks the same checkbox before pushing — if unchecked inside the pipeline, it stops and asks the user to run `/second-opinion` or explicitly skip via the checkbox.

4. **If Codex not available OR Codex review done with findings resolved**, print this VERBATIM:

> ---
>
> **All tasks executed and verified.**
>
> **Next:** Phase 6 completion. "Proceed to Phase 6"
>
> **Preview — offered again in Phase 6:**
> - `/retrospective` — engineering retrospective (coding-team's, not gstack's `/retro`)
> - `/doc-sync` — update docs to match shipped code
> - `/prompt-craft audit` — if this feature changed any skills or prompts
>
> **Shipping shortcut:** `/release` for automated release instead of manual Phase 6.
>
> ---

5. **Verify the gate is marked.** The choice (review/challenge/both/skip) should already have updated the active plan file's `- [ ] Second-opinion review` line — `/second-opinion` does the edit on review/challenge/both, and the skip branch above instructs you to do it manually. Re-read the plan to confirm the line is now `- [x]` or contains `skip:`. If it isn't, the lifecycle hook will block pipeline completion — fix the plan now.

The plan's frontmatter `status` field stays `in-progress` through this phase — it is flipped to `complete` by the orchestrator at the end of Phase 6 (see `phases/completion.md` "Final: mark plan complete"). Post-execution-review only manages the second-opinion checklist line, not the frontmatter status.

**User override:** If the user wants to skip second-opinion, edit the active plan file's Completion Checklist line to `- [x] Second-opinion review (skip: <reason>)`. The lifecycle hook reads this checkbox — verbal instructions alone will not bypass the gate.
