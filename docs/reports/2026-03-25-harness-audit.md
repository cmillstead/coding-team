# Harness Engineering Audit — 2026-03-25

Self-audit of Claude Code harness setup against own harness engineering principles (Four Verbs, Maturity Model, Golden Principles).

## Current State

**Level 3 (Measured)** with partial Level 4. 12 hooks, 16 golden principles, comprehensive skill taxonomy, identity-over-prohibition pattern embedded across all agent prompts.

## Session Context: Native Agent Migration

This audit follows the migration of 18 worker prompts from inline templates (`prompts/*.md`) to native Claude Code agent files (`~/.claude/agents/`). The hybrid architecture supports both pipeline orchestration and standalone CLI invocation (`claude --agent ct-implementer`). Life & Career Coach was added as the 8th business-team specialist.

---

## Findings

### Constrain (structural enforcement — highest priority)

#### 1. No branch-guard hook
- **Gap:** CLAUDE.md says "NEVER commit directly to main" but nothing enforces it
- **Risk:** Accidental commits to main bypass feature branch workflow
- **Fix:** PreToolUse hook on `Bash` that detects `git commit` when on main/master, exit code 2 with "Create a feature branch first"
- **Principle violated:** Constrain > Inform — structural impossibility beats instruction

#### 2. No recursive invocation hook
- **Gap:** `feedback-recursive-invocation.md` documents subagents invoking `/coding-team` recursively. Fixed at prompt level only.
- **Risk:** Prompt-level fix degrades under context pressure (documented in `feedback-context-saturation.md`)
- **Fix:** PreToolUse hook on `Skill` that blocks `/coding-team` when `coding-team-active` indicator file exists, exit code 2 with "You are already inside the coding-team pipeline"
- **Principle violated:** Constrain > Inform

#### 3. No lint-warning enforcement hook
- **Gap:** `feedback-warnings-escape-hatch.md` documents agents dismissing warnings. `pre-completion-checklist.py` checks lint *ran*, not that it *passed clean*.
- **Risk:** Named rationalization ("only warnings, no errors") is prompt-level only
- **Fix:** PostToolUse hook on `Bash` that detects warning patterns in lint/typecheck output and exit-code-2s with "Warnings are defects. Fix all warnings before proceeding."
- **Principle violated:** Constrain > Inform; Named rationalizations should be hook-enforced, not just prompt-documented

#### 4. `coding-team-active.py` uses wrong decision value
- **Gap:** Outputs `"decision": "approve"` instead of `"decision": "allow"`
- **Risk:** May be silently ignored by Claude Code hooks API
- **Fix:** Change `"approve"` to `"allow"` in the hook output

### Inform (context gaps)

#### 5. No path-specific rules
- **Gap:** Zero files in `~/.claude/rules/`. All instructions are in global CLAUDE.md.
- **Risk:** Context rot — agents load all rules even when working on a single file type. Progressive disclosure principle violated.
- **Fix:** Create `~/.claude/rules/` with:
  - `test-files.md` — real over mocks, fixture conventions, TDD discipline
  - `config-files.md` — never commit secrets, validate before deploy
  - `migration-files.md` — never modify deployed migrations, test up+down
  - `skill-files.md` — prompt-craft advisory rules for CC instruction files
- **Principle violated:** Progressive Disclosure (#4), Context Rot

#### 6. No Rust in code-style.md
- **Gap:** `rust-analyzer-lsp` plugin enabled, mockall detection in `no-mocks.py`, but no Rust style rules
- **Fix:** Add Rust section to `~/.claude/code-style.md`

#### 7. No context management guidance in CLAUDE.md
- **Gap:** `context-budget-warning.py` warns at 70/85/95% but CLAUDE.md gives no guidance on compaction strategy
- **Fix:** Add section to CLAUDE.md covering: when to compact, what to persist before compaction, how to resume after compaction, reference to the 5-layer context pipeline pattern

### Verify (observability gaps)

#### 8. No MCP health-check
- **Gap:** If codesight-mcp or QMD goes down, no indicator. Agents may silently fail on MCP calls.
- **Fix:** Status line indicator or periodic health probe. Alternatively, a PreToolUse hook on `mcp__*` that verifies server liveness before dispatching.
- **Principle violated:** Observation Is Second-Highest Leverage (#6)

#### 9. `cleanupPeriodDays` misconfigured
- **Gap:** Set as string in `env` block of settings.json, likely has no effect
- **Fix:** Move to top-level settings key as integer: `"cleanupPeriodDays": 365`

### Correct (housekeeping)

#### 10. Orphaned hook files
- **Gap:** `ctx-status.py` and `qmd-vault-embed.sh` exist in hooks directory but aren't referenced in settings.json
- **Fix:** Delete or wire up. Dead code in harness is harness entropy.

#### 11. Skill taxonomy desync
- **Gap:** These skills are referenced in CLAUDE.md / project memory but missing from `skill-taxonomy.yml`:
  - `scan-fix`
  - `a11y`
  - `api-qa`
  - `parallel-fix`
- **Fix:** Add entries with appropriate category and role mappings

---

## Priority Order

| # | Finding | Verb | Effort | Impact |
|---|---------|------|--------|--------|
| 1 | Branch-guard hook | Constrain | Low | High |
| 2 | Recursive invocation hook | Constrain | Low | High |
| 3 | Lint-warning enforcement hook | Constrain | Medium | High |
| 4 | Fix coding-team-active.py decision value | Constrain | Trivial | Medium |
| 5 | Path-specific rules | Inform | Medium | High |
| 6 | Rust in code-style.md | Inform | Low | Low |
| 7 | Context management in CLAUDE.md | Inform | Medium | Medium |
| 8 | MCP health-check | Verify | Medium | Medium |
| 9 | Fix cleanupPeriodDays location | Verify | Trivial | Low |
| 10 | Clean up orphaned hooks | Correct | Trivial | Low |
| 11 | Sync skill taxonomy | Correct | Low | Low |

## Maturity Assessment

- **Current:** Level 3 (Measured) — entropy metrics tracked, loop detection, context budget monitoring
- **Gap to Level 4 (Adaptive):** Findings 1-3 are the bridge. Prompt-level fixes for known failure modes need to become hook-level constraints. The feedback → prompt fix → hook enforcement cycle is the Level 4 flywheel.

## Meta-Observation

The pattern across findings 1-3 is the same: **a failure mode was discovered, documented in feedback memory, and fixed with prompt text — but never promoted to a hook.** The reactive harness construction flywheel (Agent fails → Human observes → Human builds constraint → Prevents recurrence) is stalling at the "prompt fix" step instead of completing to "structural constraint." Systematize the promotion: every feedback memory should be reviewed for hook-enforcement potential.
