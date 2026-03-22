# Post-Execution Review

After all tasks are executed and verified:

1. Evaluate risk signals against the completed diff. Run these commands:
   a. Count changed files: `git diff $(git merge-base HEAD main) --name-only | wc -l`
   b. If count is 5+, gate fires.
   c. Check for security-sensitive files: `git diff $(git merge-base HEAD main) --name-only | grep -iE "auth|payment|encrypt|session|token|cors|csp"`
   d. If any output, gate fires.
   e. Check for CC instruction files: `git diff $(git merge-base HEAD main) --name-only | grep -iE "phases/|skills/|prompts/|CLAUDE.md|SKILL.md"`
   f. If any output, gate fires.

2. Run: `command -v codex >/dev/null 2>&1` to check if Codex CLI is available.

3. **If ANY risk signal fired AND Codex is available**, print this VERBATIM (substitute actual values), then STOP — do not print anything after this block. Your next message depends on the user's answer:

> ---
>
> **All tasks executed and verified.**
>
> This diff [changes N files / touches security-sensitive code / modifies CC instructions / etc.].
>
> Run Codex on the full diff? Options: **review** / **challenge** (adversarial — recommended for security-sensitive changes) / **both** / **skip**
>
> ---

   - User says "review": run `/second-opinion review` against the diff. Then continue with step 3a.
   - User says "challenge": run `/second-opinion challenge` against the diff. Then continue with step 3a.
   - User says "both": run `/second-opinion review` first, then `/second-opinion challenge`. Then continue with step 3a.
   - User says "skip" or sends a different message: continue with step 4.

   3a. **After Codex review completes — findings gate.** If Codex returned ANY P1 or P2 findings:
   - List every finding with severity
   - Do NOT proceed to Phase 6. Do NOT dismiss findings as "pre-existing" or "not regressions"
   - Every finding must be: fixed (dispatch implementer), deferred (with explicit user approval), or explained as false positive (with reasoning)
   - After fixes, re-run Codex to verify. Only proceed when findings are resolved.
   - If no P1/P2 findings (only P3 or clean): continue with step 4.

4. **If no risk signals fired OR Codex not available OR Codex review done with findings resolved**, print this VERBATIM:

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

**User override:** If the user has said "never ask about second opinion" or "skip second-opinion gates" in this session, skip step 3 entirely for the rest of the session.
