# Handoff — saturation remediation, Phase 1 complete (2026-07-26)

Supersedes `2026-07-26-unstarted-work-inventory.md` and
`2026-07-26-reference-extraction-execution.md`. Every state claim below was
verified by command at write time.

## Repo state

- **`main`** @ `446046b`. **PR #123 MERGED** 2026-07-26T23:41Z; local branch deleted.
  Merged today: #118, #119, #120, #121, #122, #123.
- **Parent repo reconciled** — `~/.claude` @ `cbb8ea2` on branch
  `harness/reconcile-reference-deploy` (local, unpushed). See "The live harness"
  below.
- **No plan is `status: in-progress`** — `write-guard.py` is DORMANT. If a future
  session finds instruction edits blocked, look for a stale `in-progress` plan
  before reaching for `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`.
- **Working tree carries two pre-existing not-ours files** — `.claude/settings.local.json`
  (modified) and untracked `skills/second-opinion/codex-learnings.d/20260723-...-self-heal-migration-schema-shape.md`.
  **Never stage either.**
- Tests: `python3 -m pytest hooks/tests -q` → **1055 passed, 9 skipped**. `ruff check .` clean.

## The live harness changed — and is now recorded

`scripts/deploy.sh` ran for real during T4. `~/.claude/rules/` is **116** lines
(was 226) and `~/.claude/reference/` holds 5 symlinks, all resolving.

`~/.claude` is its own git repo (`cmillstead/claude-harness`) with
`skills/coding-team` as a **submodule**. The deploy therefore mutated the *parent*
repo's working tree — 5 symlink deletions plus an untracked `reference/` — and
left it uncommitted. Committed as `cbb8ea2`, which also bumps the submodule
pointer to `446046b`. Without that commit a `git checkout` in `~/.claude` would
silently restore five always-loaded rules and re-inflate the surface to 464 while
PR #123 sat merged and looking correct.

**That branch is local and unpushed**, on top of 5 unpushed `harness-map` commits.
It was branched from HEAD rather than `origin/main` deliberately: `origin/main`
still carries `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT: "1"` in `settings.json`, so
checking it out would have disarmed the write-guard instruction gate in live
config. Push/PR it from a `~/.claude`-rooted session.

Always-loaded surface: **464 → 354** (`config/CLAUDE.md` 238 + rules 116).

## What Phase 1 did

Created `reference/`, deployed to `~/.claude/reference/` — outside the auto-load
path. Moved 5 files there: `finding-integrity`, `codesight-fallback`,
`test-files`, `dark-features`, `mcp-resilience`. They now load only when a prompt
names them with an explicit `Read` line.

**The mechanism, which is the durable lesson:** anything under `~/.claude/rules/`
auto-loads into every session AND every subagent. `deploy.sh` puts it there.
Frontmatter (`globs:`, `alwaysApply:`, `scope:`) is **inert** — the directory is
the entire mechanism. So "extract this to `rules/`" reduces saturation by ZERO.
It had already been done twice believing the opposite.

Plan: `docs/plans/2026-07-26-reference-extraction-group-a.md` (gitignored,
`status: complete`, 1201 lines). Audit spec: `docs/reports/2026-07-26-claudemd-saturation-audit.md`.

## Open items, ranked

### 1. F3 — CORRECTED: not orphans, a two-repo split source of truth

**The original F3 in this handoff and in the audit was wrong.** It claimed 5
always-loaded files existed in no repository, with no history and no rollback. It
inferred that from their absence in *this* repo's `git ls-files` without checking
whether `~/.claude` was itself a repo. It is, and it tracks them
(`2e6a014`, `b8efdc8`). There was never a data-loss exposure.

What is real: `~/.claude/rules/` has **two owners**. Seven entries are symlinks
(`120000`) deployed from this repo; five are regular files (`100644`) owned by
the parent — `scan-finding-completeness.md` (29), `defensive-simplify-guard.md`
(16), `no-known-broken.md` (15), `text-discipline.md` (14),
`exemption-override.md` (5). That is **79 of the 116 remaining lines, now 68% of
the rules surface** — up from a third, because Phase 1 removed only from the
side this repo owns.

The consequence is measurement, not loss: anything auditing from this repo sees
37 lines and reports clean, while the real surface is 116. Later reduction phases
sized against the wrong number will undershoot.

**Resume:** do NOT move the 5 into this repo's `rules/` as the audit first
advised — two repos deploying into one directory is the defect; duplicating the
source deepens it. Pick one owner, record the decision, then extend
`deploy-drift-check.py` to walk the deployed dir and label deployed-only files by
owning repo (foreign ≠ drift).

The prune loop's `[[ -L ]]` plus its `case "$target_abs" in "$REPO_ROOT/rules/"*)`
target guard is what kept it from deleting the parent's 5 files on its first real
run. Load-bearing. The Phase 5 QA review had already caught that its test was
vacuous and fixed it.

### 2. PR #95 — open since 2026-06-24, needs a verdict

Adds `rules/interaction-mandatory.md` + 1 line to `config/CLAUDE.md`. **Its own
body's premise is backwards:** it calls the file a dark feature because "nothing
injects it", but `deploy.sh:93-96` already always-loads it. It is +22 unmetered
always-loaded lines, and its rule 1 duplicates `config/CLAUDE.md:71` — already
the most emphatic line in the harness and still violated.
**Audit verdict:** close it; re-land only its rule 2 (don't default to hooks;
consolidate) as ~4 lines, AFTER Groups B–D so it arrives on a small surface.

### 3. Remaining saturation phases (audit §5)

- **Groups B/C/D** — deletions, extractions out of `CLAUDE.md`, compressions.
  Target 354 → 163.
- **F1** — `hook-health-check.py:184-188` globs only `agents/*.md`, `phases/*.md`,
  `skills/*/SKILL.md`. Add `config/*.md` + `rules/*.md` and an aggregate check.
- **F2** — `write-guard.py:767` caps only `SKILL.md`. Extend to `config/CLAUDE.md`.
  **MUST land LAST** — at 238 lines a cap that blocks >200 would block the very
  edits that reduce it.
- **Root Cause Over Symptom rule** — UNBLOCKED. Audit says it goes after
  `# Your Role`, displacing the 45-line Engram CLI block (`CLAUDE.md:15-59`).
  Drafted text is at `docs/handoff/2026-07-24-write-guard-allowlist-and-claudemd-audit.md:19`
  — copy verbatim, it is already reviewed.

### 4. Eight P3s from the Phase 1 QA review (none blocking)

Dead cross-ref at `reference/codesight-fallback.md:20` (repo-relative, should be
absolute); `README.md:318` omits `reference/`; `ct-implementer.md:104` inline MCP
restatement drops 2 of 3 named rationalizations; `SKILL.md:88` is repo-relative
and now load-bearing; no test asserts `rules/` and `reference/` are disjoint by
basename; `ABSOLUTE_RULE_REF` arm of `test_agent_rule_refs.py` is now dormant.

### 5. `reference/` is not gated by write-guard

`BEHAVIORAL_INSTRUCTION_DIRS` (`hooks/write-guard.py:143-150`) omits **both**
`rules` and `reference`. Twelve-plus always-loaded/behavioral files any agent may
edit with no plan declaration, while conditionally-loaded `agents/*.md` ARE
gated. Fold into the F1/F2 enforcement phase — and widen it to `{"rules",
"reference"}`, not just `rules`.

### 6. Spec-silence meta-rule — PAUSED, untouched

`docs/plans/2026-07-24-spec-silence-meta-rule.md`, 497 lines, `status: planned`,
**31 tasks, 0 executed**. Declares `instruction_files: agents/ct-spec-reviewer.md,
agents/ct-qa-reviewer.md`. Blocked only on its Codex plan gate never having run.
**Resume:** run the gate, apply findings, flip to `in-progress`, execute.

### 7. `commands/` not in `scripts/deploy.sh` — QUEUED

`grep -n "commands" scripts/deploy.sh` → **zero matches**; `commands/` holds 22
files. `memory/feedback-always-route-through-build.md` records that the deployed
`/build` is a stale broken fork precisely because of this.
**Resume:** first decide whether `commands/` *should* deploy; check for collisions
with plugin-provided commands already in `~/.claude/commands/`.

### 8. Self-modifying hook — BLOCKED ON A HUMAN DECISION

`docs/tickets/2026-07-25-self-modifying-hook-no-safe-edit-path.md`, four options
at `:46-54`, none picked. Do not pick for the operator.

### 9. Pre-existing test failure — NOT ours

`skills/second-opinion/scripts/test_build_digest.py::test_design_face_output_is_byte_identical_to_committed_digest`
fails because the untracked `codex-learnings.d/20260723-...` entry renders into
the generated digest but is absent from the committed one. Root-caused by command
this session. Outside `pytest hooks/tests` scope, which is why the baseline reads
green. **Resolution is the operator's:** commit the entry and regenerate, or
delete the file.

## Operating rules learned this session — apply these

1. **Dispatch agents WITHOUT `name` when you need the result inline.** Passing
   `name` silently forces background and overrides `run_in_background: false`,
   costing you the report. Measured by controlled probe (A vs B, byte-identical
   but for `name`). Saved to `memory/feedback-agent-idle-without-report.md`.
2. **`SendMessage` lands ~75–90 seconds later.** Usable for a multi-minute agent,
   useless for course-correction. Assuming a slow message was a lost message
   caused this session's only self-inflicted defect — a hand-patched plan task
   placed after T7 while its body said "run before T4."
3. **Verify every agent state claim by command.** Three agents made confident
   false claims this session (wrong branch in a report header; "branch-name-sensitive
   digest" for what was an untracked file; "your check failed because docs/plans
   is gitignored" when the check was `ls`). Their file-CONTENT analysis was
   consistently excellent. Reject the premise, keep the analysis.
4. **The QA review at the exit gate earned its cost** — 12 findings, 4 of them
   P2 defects in this session's own work, including a vacuous test that stayed
   green with its guard deleted.
