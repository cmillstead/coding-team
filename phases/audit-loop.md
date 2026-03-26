# Audit Loop

## Audit Team Dispatch

After the completeness check passes and implementer reports DONE or DONE_WITH_CONCERNS:

1. Record HEAD_SHA, collect modified files list (git diff --name-only BASE..HEAD).
   Also run `mcp__codesight-mcp__get_changes` with `repo_path` set to the working directory, `git_ref: "BASE..HEAD"`, and `include_impact: true` to get a symbol-level diff with downstream impact analysis. Pass BOTH the file list AND the symbol-level changes to each auditor.
   After recording changes, run `mcp__codesight-mcp__invalidate_cache` for the repo so auditors see fresh symbol data reflecting the implementer's commits.
   **Pre-compute for spec reviewer:** Run `git log --oneline BASE..HEAD` and include the output in the spec reviewer's `## Git History` section. The spec reviewer has no Bash tool — it cannot run git commands itself.
2. Dispatch audit agents IN PARALLEL via Agent tool (spec reviewer and simplify auditor as read-only Explore; harden auditor and harness engineer as general-purpose to allow Bash tool access):
   a. Spec reviewer (see ~/.claude/agents/ct-spec-reviewer.md) — "does it match the spec? was TDD followed?"
   b. Simplify auditor (see ~/.claude/agents/ct-simplify-auditor.md) — "is there a simpler way?"
   c. Harden auditor (see ~/.claude/agents/ct-harden-auditor.md) — "what would an attacker try?"
   d. Prompt-craft auditor (see ~/.claude/agents/ct-prompt-craft-auditor.md) — triggers when BOTH:
      (i) Task has PROMPT_CRAFT_ADVISORY annotation, AND
      (ii) Modified files include at least 1 file matching: `phases/*.md`, `agents/*.md`, `prompts/*.md`, `skills/*/SKILL.md`, `SKILL.md`, `CLAUDE.md`, `memory/*.md`
      Both conditions required (belt and suspenders). If either is missing, skip this auditor.
   e. Harness engineer (see ~/.claude/agents/ct-harness-engineer.md) — triggers when modified files include at least 1 file matching: `settings.json`, `hooks/*`, `rules/*`, `*.claude/CLAUDE.md`, `agents/*.md`
      Dispatch as general-purpose (needs Bash for hook inspection). If no harness files in the diff, skip.
3. Triage findings (see Audit Triage below)
4. If findings to fix → dispatch new implementer to fix → re-audit (max 3 rounds)
   Fresh audit agents each round — don't reuse.
   After the implementer applies audit fixes: re-run tests to verify fixes didn't introduce regressions. This is mandatory.

**Audit agents MUST be read-only (Explore) — except harden auditor which needs Bash for dependency audit commands.** This prevents reviewers from silently "fixing" things instead of flagging them. The separation between finding and fixing is the whole point.

**Fresh audit teammates each round.** Don't reuse auditors — carried context biases toward "already checked" areas.

**Zero-findings scrutiny:** If any auditor reports zero findings on a diff
touching 5+ files or 200+ changed lines, verify the auditor actually
read the files (check for file:line references in methodology). "Zero
findings" on a large diff may indicate the auditor ran but didn't engage.
Re-dispatch once with: "Your previous review found zero findings on a
N-file/N-line diff. Confirm by citing specific code sections you reviewed."

## Audit Triage

After collecting findings from all auditors:

**Refactor gate:** For any finding categorized as "refactor" (not a bug or security issue), apply this bar: *"Would a senior engineer say this is clearly wrong, not just imperfect?"* Reject style preferences and marginal improvements.

**Severity routing:**
- **Critical/High** — implementer fixes immediately, re-audit
- **Medium** — include in next fix round
- **Low/Cosmetic** — fix inline if trivial, otherwise note in completion summary and skip

**Budget check:** If fix rounds add 30%+ to the original implementation diff, tighten scope — skip medium/low simplify findings, focus on harden patches and spec gaps.

**Drift check (between audit rounds):** Before spawning the next audit round, re-read the original task description. If findings are pulling into unrelated areas or scope has expanded beyond the task, re-scope or exit the audit loop.

**BLOCKED auditors:** If any auditor reports Status: BLOCKED, do NOT proceed to the fix round. Investigate the blocker — usually missing files, empty file list, or insufficient context. Re-dispatch the blocked auditor with additional context (e.g., read the missing files and include their contents). If the blocker persists after 2 retries, surface to the user with the BLOCKED reason.

## Audit Loop Exit

Exit when ANY are true:
1. **Clean audit** — all auditors report zero findings
2. **Low-only round** — all remaining findings are low severity, fix inline
3. **Loop cap reached** — 3 audit rounds completed. Fix remaining critical/high inline, log unresolved medium/low in completion summary.
   **Cross-model escalation:** If medium+ findings remain unresolved AND `command -v codex >/dev/null 2>&1` succeeds, offer: "Audit loop capped with N unresolved findings. Run `/second-opinion challenge` on the diff for a cross-model perspective? (Y/n)". If yes, run it and triage any new findings. If no or Codex unavailable, proceed.
