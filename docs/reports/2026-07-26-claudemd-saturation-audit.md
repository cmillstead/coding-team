# CLAUDE.md Saturation Audit — 2026-07-26

**Auditor:** ct-harness-engineer
**Repo:** `/Users/cevin/.claude/skills/coding-team`
**Branch at audit time:** `fix/write-guard-plan-allowlist`
**Scope:** the always-loaded instruction surface — `config/CLAUDE.md` + all `~/.claude/rules/*.md` (12 files at audit time; **7 today**, after Group A relocated 5)
**Status:** COMPLETE — **arithmetic reconciled 2026-07-27, see §0.1**

---

## 0. Headline

**Numbers below are AS OF THE AUDIT (2026-07-26, pre-Group-A). For current
figures and the corrected roll-up, read §0.1 — it supersedes this table.**

| | Lines (at audit time) |
|---|---|
| Current always-loaded surface | **464** |
| `hook-health-check.py` saturation threshold | **200** |
| Overage | **2.32x** |
| Projected after all recommendations | ~~163~~ → **187** (see §0.1) |
| Net delta | ~~−301 (−65%)~~ → **−277 (−60%)** (see §0.1) |
| Headroom under threshold after landing the Root Cause rule | ~~37 lines~~ → **13 lines**, or **−51** counting `MEMORY.md` (see §0.1) |

**The root cause of "you ignore all your standing rules" is not any individual rule. It is that the harness measures the wrong surface.** `hook-health-check.py:184-188` globs `agents/*.md`, `phases/*.md`, `skills/*/SKILL.md` — and nothing else. `config/CLAUDE.md` and `rules/*.md` are outside the glob. The one surface loaded into *every* session and *every* subagent is the only instruction surface with **no line cap, no warning, and no block**. It has grown to 2.32x the threshold the harness enforces everywhere else, unobserved. This is a Golden Principle #6 failure (Observation Is Second-Highest Leverage) at the exact point where observation matters most.

*(Root-cause diagnosis above stands and was confirmed by implementation. The measurement gap it identifies is **CLOSED** as of F1 — `check_always_loaded_surface()`, merged 2026-07-27 in PR #125. Its `hook-health-check.py:184-188` citation has since drifted; the per-file check is now `check_instruction_file_lengths()` at `:192`. Cite by symbol.)*

---

## 0.1 Arithmetic reconciliation (added 2026-07-27)

**This section supersedes §0's projections and §5's roll-up line.** Three defects,
all in the roll-up rather than in any individual group subtotal:

**1. The reduction column does not sum to the printed target.** Every group
subtotal in §5 is internally correct, but the total is not:

```
Current always-loaded (at audit)                     464
  Group A  relocations rules/ -> reference/         -110   -> 354   [LANDED]
  Group B  deletions (enforced / dead)               -42   -> 312
  Group C  extractions out of CLAUDE.md              -93   -> 219
  Group D  compressions                              -44   -> 175
  Group E  additions (incl. Root Cause rule)         +12   -> 187
                                                    -----
Projected always-loaded                              187   (printed: 163 — WRONG)
Net delta                                           -277   (printed: -301 — WRONG)
```

The printed **163** is 24 lines below what the groups actually deliver, and the
printed **−301** overstates the reduction by 24. Headroom under the 200 threshold
is therefore **13 lines, not 37**.

**The 24-line gap has a traceable cause: two incompatible estimation methods.**
The **163** is a *bottom-up* end-state estimate (§5's Final-state note:
`CLAUDE.md ≈100 + rules ≈63`). The column is *top-down* subtraction. From today's
measured 354, bottom-up demands **−191** of remaining reduction (238→100 is −138,
116→63 is −53) while groups B+C+D+E enumerate only **−167**. So **24 lines of
reduction are missing from the group breakdown** — the enumeration is incomplete
relative to its own target, not merely mis-added.

**Do not execute Groups B/C/D until this is settled.** Either extend the groups to
name the missing 24 lines, or restate the target as **187 / 13 lines of headroom**.
The two readings imply materially different amounts of work.

**2. Group A has LANDED, so 464 is no longer the starting point.** Group A's −110
shipped 2026-07-26 (PR #123, reference extraction). The surface measured
**354** today, which is exactly 464 − 110 — an independent confirmation that
Group A's subtotal was correct. Remaining work is B + C + D + E = **−167**, taking
354 → 187. Every bare `464` elsewhere in this document is an at-audit figure, not
a current one.

**3. `MEMORY.md` is unmeasured, and it inverts the conclusion.**
`~/.claude/projects/<slug>/memory/MEMORY.md` also auto-loads into every session and
every subagent — **65 lines today** (64 the day before; it grows with every feedback
memory that lands). Neither this audit nor F1's `check_always_loaded_surface()`
measures it.

Counting it: the true always-loaded surface today is ~**419** (354 + 65), and after
all reductions it would be ~**251** (187 + 65) — **still over the 200 threshold**.
The reductions would complete, the plan would report success, and the warning would
keep firing.

**This is a scope decision for the operator, not a bug.** Folding `MEMORY.md` into
the measurement makes the reported number project-dependent, which is a real design
cost. The options are: (a) count it and extend the reductions to cover it, (b) leave
it out and accept that the reported number is a floor, or (c) revisit the 200
threshold. F1's docstring currently names it as a known-unmeasured contributor and
calls the reported figure a floor, which is honest but does not resolve the target.

---

## 1. The mechanism, corrected

Three findings about *how* these files load. All three are verifiable from this subagent's own system prompt.

### 1.1 `~/.claude/rules/*.md` loads unconditionally. Frontmatter is inert.

Three frontmatter dialects are in use across the 12 files:

| Dialect | Files | Honored? |
|---|---|---|
| `globs: [...]` | `config-files.md:2-8`, `dark-features.md:2-7`, `test-files.md:2-9` | **No** |
| `alwaysApply: true` | `hook-bypass.md:2`, `mcp-resilience.md:2` | Vacuously |
| `scope: always-loaded` / `always-on` | `no-known-broken.md:3`, `scan-finding-completeness.md:3`, `defensive-simplify-guard.md:3` | Vacuously |
| (none) | `finding-integrity.md`, `codesight-fallback.md`, `exemption-override.md`, `text-discipline.md` | Loads anyway |

**Evidence:** this audit session touched no `*.py`, no test file, and no `*.json` config before the system prompt was assembled — yet `test-files.md`, `config-files.md`, and `dark-features.md` are all present verbatim in it, alongside every no-frontmatter file. The glob filter is not applied. Presence in `~/.claude/rules/` is the whole mechanism.

**Consequence:** every extraction target must be verified against this. Moving a section from `config/CLAUDE.md` into `rules/` is a **no-op for saturation** — `scripts/deploy.sh:93-96` copies every `rules/*.md` (except `README.md`) straight into `~/.claude/rules/`.

### 1.2 The proven on-demand mechanism

`~/.claude/golden-principles.md` (59 lines), `~/.claude/code-style.md` (50), and `~/.claude/command-hygiene.md` (29) sit at the `~/.claude/` **root**, are deployed by `scripts/deploy.sh:99-103`, and are **absent** from this session's system prompt. `agents/reference/harness-engineer-reference.md` (25.3K) is likewise absent and is read only because `agents/ct-harness-engineer.md` instructs it explicitly.

**So the mechanism that works is:** file lives anywhere *except* `~/.claude/rules/` and `~/.claude/CLAUDE.md`, and an agent prompt / phase file / skill file contains a literal `Read <path>` instruction. That is conditional — only the dispatched agent pays, and only when dispatched. **Every extraction in §5 names this mechanism and its trigger.**

### 1.3 The `rules/` extraction inverted its own goal

`rules/finding-integrity.md:1-4` and `rules/codesight-fallback.md:1-4` carry this comment:

> `<!-- This file has NO globs frontmatter on purpose — it is not an auto-load rule. It is a dispatch-context include: agent prompts point here... -->`

**That premise is false.** Both files auto-load into every session. These two were extracted from 6 duplicated agent prompts to *reduce* context cost. The result: content that previously appeared once per dispatched agent (and only in that agent's window) now appears in **every** session AND is still re-read by each of the 6/5 agents that point at it. The de-duplication **increased** total always-loaded cost by 49 lines and produced double-delivery for subagents.

---

## 2. Full rule enumeration and classification

Buckets: **AE** = already-enforced (hook cited) · **M** = mechanizable · **NME** = not-mechanizable-essential · **S** = situational.

### 2.1 `config/CLAUDE.md` (238 lines)

| # | `file:line` | Rule | Bucket | Enforcement / disposition |
|---|---|---|---|---|
| 1 | `:1-7` | Engineering-manager identity; all code routes through `/coding-team` | **AE** | `hooks/write-guard.py:261` `check_phase5` → dispatched `:1036`, **blocks**. Identity framing is the compliance mechanism (GP#5); keep the identity, it is 7 lines. |
| 2 | `:7` | Implementer carve-out at `agents/ct-implementer.md:27-31` | NME | Verified: carve-out is at `:27-31`. Reference is live. |
| 3 | `:15-59` | Engram CLI command reference (45 lines) | **S** | Zero behavioral content. Pure syntax reference. → §5 R1 |
| 4 | `:63-67` | Check memory before starting | NME | Keep, compress. |
| 5 | `:66` | ContextKeep `list_all_memories` / `retrieve_memory` | **DEAD** | No `contextkeep` server in `~/.claude/.mcp.json` (only `base-mcp`); no match in `settings.json` or `settings.local.json`. → §4 C6 |
| 6 | `:71` | Number your options `1.`/`2.` | **NME** | No hook possible (governs prose the model emits). Already the most emphatic line in the file — and still repeatedly violated. See §6b. |
| 7 | `:72` | Commit style `feat:`/`fix:`/`test:`/`docs:` | **M** (declined) | `hooks/git-safety-guard.py:215` `extract_commit_message` and `:75` `_extra_prefix_ok` already parse the message. Adding a prefix *block* is 1 line of hook change but a cosmetic failure — does not meet "prevents real damage." **Keep as prose.** |
| 8 | `:73` | Don't summarize what you just did | **NME** | Recurrent violation (recorded verbatim in the 2026-07-24 handoff). Partially contradicted — §4 C5. |
| 9 | `:77-81` | Rules are global by default | NME | Keep. |
| 10 | `:83-89` | A session stays in the directory it started in | **M** (declined) | High damage (cross-repo harness edits), but detection requires comparing `cwd` to the edit target across an unbounded repo set. `hooks/write-guard.py:983` `check_path_safety` is the nearest existing seam and is advisory-only. **Keep as prose.** |
| 11 | `:91-94` | Exception: appending a rule is allowed from any session | NME | Keep — it is the resolver for #10. |
| 12 | `:98-104` | Handoff triggers (added today, PR #119 / `6164e43`) | **S + duplicate** | → §6c |
| 13 | `:106-110` | Compaction awareness (50/70/80%) | NME | Keep. `:109` duplicates `:101`. |
| 14 | `:112-116` | What to persist before compaction | NME | Keep — must be in context *at* compaction; a file read cannot be relied on then. |
| 15 | `:118-123` | Resuming after compaction | NME | Keep — same reason. |
| 16 | `:125-139` | Model routing table — explicitly *"for coding-team agents, NOT for you"* | **S** | Self-declared irrelevant to the reader who always loads it. → §5 R6 |
| 17 | `:141-158` | Testing: real over mocks (18 lines) | **AE** | `hooks/write-guard.py:643` `check_no_mocks` → dispatched `:1054`, **blocks**, with `# mock-ok:` escape hatch (`write-guard.py:220`). Also restated at `rules/test-files.md:15`, `config/CLAUDE.md:165`, `SKILL.md:80`. **Quadruple coverage.** → §5 R8 |
| 18 | `:163` | Run tests and linting before committing | **AE** (advisory) | `hooks/git-safety-guard.py:1084-1090` PRE-COMPLETION CHECKLIST. Advisory, not blocking → keep 1 line. |
| 19 | `:164` | Follow the project's layer structure; read AGENTS.md/ARCHITECTURE.md | NME | Keep. |
| 20 | `:165` | Use real implementations, never mocks | **AE / dup** | Third copy of #17. Delete. |
| 21 | `:166` | Check existing utilities, TDD, store decisions in ContextKeep | **partly DEAD** | ContextKeep unconfigured (see #5). Reword. |
| 22 | `:167` | Descriptive names, no single-letter variables | **S** | Duplicated in `~/.claude/code-style.md` (already on-demand). Delete. |
| 23 | `:170-175` | Ask First — deps, schema, public API, shared-file deletes, CI config, 4+ files | NME | Keep. `:175` (4+ files) partially observable but no hook counts a task's file span. |
| 24 | `:178` | NEVER commit secrets | **AE** | `hooks/git-safety-guard.py:990` `is_secret_file` per staged file, **blocks**; `:976` `is_broad_add` blocks `git add -A`/`.`. |
| 25 | `:179` | NEVER modify deployed migration files | **AE** | `hooks/write-guard.py:539` `check_migration` → dispatched `:1048`, **blocks**. |
| 26 | `:180` | NEVER skip or disable tests | **AE** | `hooks/write-guard.py:643` (mock/skip patterns) + `rules/test-files.md:19-20`. |
| 27 | `:181` | NEVER force push to main/release | **AE** | `hooks/git-safety-guard.py:1012` `is_protected_branch`, **blocks**. |
| 28 | `:182` | NEVER commit directly to main/master | **AE** | Same — `git-safety-guard.py:1012`, **blocks**. |
| 29 | `:183` | NEVER commit `.env` | **AE / dup of #24** | `git-safety-guard.py:990`. |
| 30 | `:184` | NEVER use `any` in TypeScript | **S** | Belongs in `code-style.md` (on-demand). |
| 31 | `:185` | NEVER swallow errors with empty catch | **S** | Belongs in `code-style.md`. |
| 32 | `:186` | NEVER introduce a framework without approval | NME | Duplicates `:170`. Merge. |
| 33 | `:187` | NEVER claim done without verification | **AE** (advisory) | `git-safety-guard.py:1084-1090`; GP#7. Keep 1 line. |
| 34 | `:188` | After 3 failed attempts, STOP and report | **AE** | `hooks/loop-detection.py:19` `MAX_RETRIES = 3`, fires at `:168`. Advisory injection, not a block. Keep 1 line. |
| 35 | `:190-210` | Proactive skill-suggestion table (21 lines, 15 rows) | **S / M** | A routing table. → §5 R7 |
| 36 | `:212-214` | Code style pointer | NME | Keep (3 lines, correct pattern). |
| 37 | `:216-218` | Command hygiene — compound block "disabled UNCONDITIONALLY on this machine" | **DEAD-ish** | 3 always-loaded lines describing a **disabled** mechanism. → §4 C8 |
| 38 | `:220-222` | Golden principles pointer | NME | Keep. Correct on-demand pattern; existence proof for §1.2. |
| 39 | `:224-227` | UI/UX standards — "(for coding-team agents)" | **S** | Self-declared not-for-the-reader. → §5 R9 |
| 40 | `:229-231` | Hook deployment order (deploy before settings) | **AE (structurally)** | `scripts/deploy.sh` deploys hooks at `:36` and touches `SETTINGS` at `:116` — order is enforced by construction. Residual risk is hand-editing `settings.json`. Compress to 1 line. |
| 41 | `:233-238` | Obsidian vault layout | **S** | Relevant only to `/save`. → §5 R10 |

### 2.2 `~/.claude/rules/*.md` (226 lines at audit — **116 across 7 files today**, after Group A)

| File | Lines | Explicit readers (repo) | Bucket | Disposition |
|---|---|---|---|---|
| `finding-integrity.md` | 28 | **6 agents**, each with a literal `Read ~/.claude/rules/finding-integrity.md before starting` (`ct-spec-reviewer.md:143`, `ct-harden-auditor.md:107`, `ct-simplify-auditor.md:116`, `ct-qa-reviewer.md:126`, `ct-prompt-craft-auditor.md:108`, `ct-harness-engineer.md:74,:181`) | **S** | → R2. Loading mechanism already exists and is conditional. |
| `codesight-fallback.md` | 21 | **5 agents** (`ct-spec-reviewer.md:129`, `ct-harden-auditor.md:77`, `ct-simplify-auditor.md:90`, `ct-qa-reviewer.md:101`, `ct-harness-engineer.md:91`) | **S** | → R2. Same. |
| `test-files.md` | 21 | `ct-qa-reviewer.md:85`, `ct-spec-reviewer.md:74`, `SKILL.md:80` | **AE + S** | Blocked by `write-guard.py:643`. → R2. |
| `dark-features.md` | 19 | `ct-implementer.md:189` | **S** | → R2. |
| `mcp-resilience.md` | 21 | `ct-simplify-auditor.md` only | **S** | → R2, but needs a `Read` line added to the other agents first (see R2 precondition). |
| `config-files.md` | 18 | **ZERO** | **AE + dead weight** | `:14` (no secrets) = `git-safety-guard.py:990`. `:15-17` are unenforced style preferences with no consumer. `:18` duplicates `CLAUDE.md:174`. → R3, **delete**. |
| `hook-bypass.md` | 19 | `phases/named-rationalizations.md` | **NME** | Keep. A meta-rule about hooks cannot be enforced by a hook. Strip inert frontmatter `:1-4` + deploy comment `:7`. |
| `text-discipline.md` | 14 | **ZERO** | **NME** | Keep — recurrent, lead-scoped, unmechanizable. But see §4 C2: its own scope statement is contradicted by its delivery. |
| `no-known-broken.md` | 15 | `phases/named-rationalizations.md` | **NME** | Keep core; strip frontmatter `:1-4` and `## Why` `:13-15`. |
| `scan-finding-completeness.md` | 29 | `phases/named-rationalizations.md` | **NME + S** | Split: the 2 core paragraphs stay always-loaded; `:22-23` (context-constrained handoff) and `:25-29` (`## Why`) move to reference. |
| `defensive-simplify-guard.md` | 16 | **ZERO** | **NME** | Keep — it is the *only* control over `/simplify` (an unhookable built-in). Strip frontmatter + `## Why`. |
| `exemption-override.md` | 5 | **ZERO** | **NME** | Keep. Fix dead path at `:5` — see §4 C7. |

**Mechanizable bucket: 2 entries, both DECLINED** (#7 commit-prefix, #10 session-directory). Neither meets the "prevents real damage" bar in `memory/feedback-hooks-reliability-budget.md`. **This audit proposes ZERO new hooks.** It proposes two changes to *existing* hooks (F1, F3), which is the consolidation path `memory/feedback-hooks-reliability-budget.md` and GP#11 prescribe.

---

## 3. Structural findings

### F1 — P1 · Verify · observability · The saturation guard cannot see the saturated surface

- **Component:** `hooks/hook-health-check.py:184-188`
- **Gap:** `instruction_globs = ["agents/*.md", "phases/*.md", "skills/*/SKILL.md"]`. Neither `config/CLAUDE.md` nor `rules/*.md` is covered. The 200-line check at `:196` therefore never fires on the 464-line always-loaded surface.
- **Risk:** This is the root cause. The surface grew from 226→238 today and 464 total with zero signal. Every future session inherits the drift.
- **Fix:** add `"config/*.md"` and `"rules/*.md"` to the glob list at `:184-188`, and add a distinct aggregate check: sum of `config/CLAUDE.md` + all `rules/*.md` against 200, reported separately at `:651-655`. **No new hook** — two edits inside an existing SessionStart hook that already runs.
  **IMPLEMENTED 2026-07-26 differently, and deliberately:** adding globs to `check_instruction_file_lengths` was rejected on two independent grounds. (i) Its `repo_root` is `Path(__file__).parent.parent` and `Path(__file__)` is NOT symlink-resolved, so the root is `~/.claude` when the hook runs deployed but this repo when pytest loads the module — a `"rules/*.md"` glob there would report the deployed 7 files (116 lines) in production but this repo's 3 files (61 lines, including a `README.md` that is not deployed and not always-loaded) under pytest — two different numbers over two different file sets, and no test could pin the production one. (ii) It is a PER-FILE check, and individual rules run 5-29 lines, so a 200-line threshold would never fire on them at any root. A separate aggregate `check_always_loaded_surface()` reads `~/.claude/CLAUDE.md` + `~/.claude/rules/*.md` via `Path.home()`, which is stable across both load paths. Warning-only; the per-file 200-line check is unchanged.
- **Principle:** GP#6 Observation Is Second-Highest Leverage; `memory/feedback-context-saturation.md`.
- **Effort:** Trivial · **Impact:** High · **Core**

### F2 — P1 · Constrain · context · No blocking line cap on the always-loaded surface

- **Component:** `hooks/write-guard.py:767` — `SKILL_MD_PATTERN = re.compile(r"\.claude/skills/.*/SKILL\.md(\.tmpl)?$")`
- **Gap:** `check_skill_line_cap` (`:770`, dispatched `:1060`) **blocks** a SKILL.md over 200 lines. `config/CLAUDE.md` — loaded far more often than any SKILL.md — has no cap at any level.
- **Risk:** `SKILL.md` currently sits at 198/200 and cannot be appended to. `config/CLAUDE.md` sat at 226 and was appended to today without friction. The harness's strictest control and its weakest control are inverted relative to blast radius.
- **Fix:** extend `SKILL_MD_PATTERN` to a tuple of patterns including `config/CLAUDE\.md$` and `\.claude/CLAUDE\.md$`, and generalize the message at `:809-813`. **No new hook** — one existing blocking check, widened.
- **Principle:** GP#3 Negative Rules Are Stronger; leverage ordering Constrain > Inform.
- **Effort:** Low · **Impact:** High · **Core**

### F3 — P2 · Verify · observability · Deployed-only files are invisible to drift detection

> **CORRECTION, 2026-07-26 (post-Phase 1).** This finding originally claimed the
> 5 files were untracked, with "no git history, no review, no rollback." **That is
> false.** They are committed content of the parent `claude-harness` repo. The
> original text inferred "no repository" from their absence in *this* repo's
> `git ls-files` without checking whether the directory above was a repo. It is.
> The observability gap below is real; the data-loss risk was not. See
> `memory/feedback-nested-repo-blind-spot.md`.

- **Component:** `hooks/deploy-drift-check.py:19-22` — *"Only files that exist in source are checked (deployed-only files are ignored)."*
- **Topology (verified by command):** `~/.claude` is a git repo (`cmillstead/claude-harness`) that tracks `rules/` directly and carries `skills/coding-team` as a **submodule** (`.gitmodules`). So `~/.claude/rules/` has **two owners**: **2** symlinks (mode `120000`) deployed from this repo, and **5** regular files (mode `100644`) owned by the parent — 7 entries, 116 lines total (37 + 79). *(Count corrected 2026-07-26: the original "7 symlinks" was pre-Phase-1; Phase 1 moved 5 symlinked rules to `reference/`.)*
- **Gap:** the 5 parent-owned files — `scan-finding-completeness.md` (29), `defensive-simplify-guard.md` (16), `no-known-broken.md` (15), `text-discipline.md` (14), `exemption-override.md` (5), **79 lines, 68% of the post-Phase-1 rules surface** — are invisible to any audit or drift check that starts from this repo. They have history (`2e6a014`, `b8efdc8`); they are simply owned one level up.
- **Risk:** not data loss — **split source of truth.** A drift check rooted here sees 2 of 7 always-loaded files and reports clean. Anyone reading only this repo will conclude the rules surface is 37 lines when it is 116, and will size later reduction phases against the wrong number.
- **Fix:** (a) **do NOT move the 5 into this repo's `rules/`** as originally advised — two repos deploying to one directory is the actual defect, and duplicating the source makes it worse. Decide ownership explicitly, in one direction, and record it. (b) **CORRECTED 2026-07-26:** the measurement gap is closed in `hooks/hook-health-check.py`, **not** in `deploy-drift-check.py`. `find_drift` is scoped to `SOURCE = ~/.claude/skills/coding-team/hooks` vs `DEPLOYED = ~/.claude/hooks` and compares only `*.py` — it cannot measure `rules/*.md` under any extension, so extending it could not have produced the number this finding needs. The correct fix is the aggregate `check_always_loaded_surface()` added to `hook-health-check.py`, which reads the DEPLOYED `~/.claude/CLAUDE.md` + `~/.claude/rules/*.md` and therefore spans both owners by construction — no ownership decision required for the measurement to be correct. **No new hook** — one existing SessionStart hook, one added check.
- **Principle:** GP#2 Repository Is Source of Truth.
- **Effort:** Low · **Impact:** High · **Core**

### F4 — P2 · Inform · context · The `rules/` extraction pattern is a saturation trap

- **Component:** `scripts/deploy.sh:93-96`; `rules/finding-integrity.md:1-4`; `rules/codesight-fallback.md:1-4`
- **Gap:** `rules/` is documented (in its own files) as a dispatch-context include directory. It is in fact an always-load directory. Any future "extract this to `rules/`" refactor will *increase* the always-loaded surface while its authors believe it is decreasing it. This has already happened twice.
- **Risk:** the trap is self-reinforcing — the more the harness extracts to `rules/`, the more saturated it gets, the less any rule binds.
- **Fix:** introduce `reference/` in the repo, deployed to `~/.claude/reference/` by a new `deploy.sh` loop mirroring `:93-96`. Move dispatch-context files there (R2). Correct the false comments at `finding-integrity.md:1-4` and `codesight-fallback.md:1-4`. Add a line to `rules/README.md` stating that **anything placed in `rules/` is always-loaded in every session and every subagent, and frontmatter does not change that.**
- **Principle:** GP#4 Progressive Disclosure; GP#11 Consolidate Before Adding.
- **Effort:** Medium · **Impact:** High · **Core**

### F5 — P3 · Inform · context · Frontmatter is decorative across three dialects

- **Component:** all 12 `~/.claude/rules/*.md` (see §1.1 table)
- **Gap:** 46 lines of frontmatter and deploy-source comments across the rules surface encode conditional-loading intent that the runtime does not honor. The `globs:` blocks alone are 27 lines of always-loaded YAML that does nothing.
- **Risk:** authors write `scope: always-on` (PR #95) or `globs:` and believe they have scoped the cost. They have not. Compounds F4.
- **Fix:** strip inert frontmatter from every file that stays in `rules/`. Retain a one-line `<!-- always-loaded: every session, every subagent -->` marker so the cost is stated where it is paid.
- **Principle:** GP#15 Error Messages Are Instructions (inverse: config that lies about its effect).
- **Effort:** Trivial · **Impact:** Medium · **Core**

---

## 4. Contradictions and dead references

Every path below was checked by command.

| ID | Location | Problem | Verified how |
|---|---|---|---|
| **C1** | `rules/finding-integrity.md:1-4`, `rules/codesight-fallback.md:1-4` | Comment asserts *"it is not an auto-load rule"*. Both auto-load. | Both appear verbatim in this session's system prompt. |
| **C2** | `rules/text-discipline.md:7-8` | *"Subagents dispatched via the Agent tool do NOT inherit this rule"* — yet the file is in this subagent's system prompt. The rule's stated scope is contradicted by its delivery mechanism. | Present in this subagent's system prompt. |
| **C3** | `config/CLAUDE.md:101` vs `:109` | 80% compaction trigger stated twice, 8 lines apart, in two different lists. | Read. |
| **C4** | `config/CLAUDE.md:143` | *"see `rules/test-files.md` for the base rule"* — then restates the base rule in full at `:145-158`. Four total copies (see rule #17). | Read + `grep` across `agents/`, `SKILL.md`. |
| **C5** | `config/CLAUDE.md:73` vs `rules/text-discipline.md:12` | `:73` "Don't summarize what you just did"; `text-discipline.md:12` "a one-line past-tense post-mortem is correct, not under-communicated." Reconcilable, but they pull opposite ways and the operator has flagged `:73` as violated. | Read both. |
| **C6** | `config/CLAUDE.md:66`, `:166` | **ContextKeep is not configured.** `~/.claude/.mcp.json` contains only `base-mcp`; no `contextkeep` match in `settings.json` or `settings.local.json`. Two always-loaded lines instruct the agent to use a tool that does not exist. | `cat ~/.claude/.mcp.json`; `grep -il contextkeep settings*.json` → no match. |
| **C7** | `rules/exemption-override.md:5` | References `named-rationalizations.md:28` with a bare filename. From `~/.claude/rules/` that resolves to `~/.claude/rules/named-rationalizations.md`, which **does not exist**. The real file is `skills/coding-team/phases/named-rationalizations.md` — and `:28` does contain the scoped-vs-unscoped text, so the *content* claim is correct; only the path is unresolvable. | `find ~ -maxdepth 6 -name "named-rationalizations*"` → single hit under `phases/`. `sed -n '28p'` confirms content. |
| **C8** | `config/CLAUDE.md:216-218` | Describes the compound-command block, then states it *"is currently disabled UNCONDITIONALLY on this machine."* Three always-loaded lines whose net instruction is "this is recommended but not enforced." | Read; `hooks/git-safety-guard.py:773` `_compound_allow_overridden`. |
| **C9** | `config/CLAUDE.md:125` header | *"(for coding-team agents, NOT for you)"* — 15 lines the always-loaded reader is told to ignore. Same pattern at `:224` *"(for coding-team agents)"*. | Read. |
| **C10** | `config/CLAUDE.md:165` vs `:143-158` vs `rules/test-files.md:15` vs `SKILL.md:80` | Mocks rule stated four times, three of them always-loaded, on top of a blocking hook. | Read + grep. |
| **C11** | PR #95 body | Claims `interaction-mandatory.md` is a dark feature ("nothing injects the file at runtime"). **False** — `scripts/deploy.sh:93-96` deploys it to `~/.claude/rules/`, which auto-loads. See §6b. | `sed -n '86,98p' scripts/deploy.sh`. |

**No dead references found** for: `~/.claude/command-hygiene.md`, `~/.claude/code-style.md`, `~/.claude/golden-principles.md` (GP#17 confirmed at `:57`), `phases/task-weight.md`, `agents/ct-implementer.md:27-31`, `~/Documents/obsidian-vault/`, and all 5 hooks referenced by `session-start-dispatcher.py` / `prompt-dispatcher.py` outside the repo (`context-staleness-check.py`, `weekly-synthesis-check.py`, `session-capture-check.py`, `proactive-recall.py`, `mid-session-recall.py` — all exist at `~/.claude/hooks/`). Those 5 are, however, **also untracked by this repo** — same class as F3, flagged there.

---

## 5. Recommendations with line arithmetic

Every extraction names its loading mechanism and whether that mechanism is conditional.

### Group A — ✅ **LANDED 2026-07-26 (PR #123)** — relocations out of `rules/` (mechanism: existing literal `Read <path>` in agent prompts; conditional = YES, only the dispatched agent pays)

*(Delivered its full −110. The surface measured 354 afterwards = 464 − 110, independently confirming this subtotal. Groups B/C/D remain PENDING and are blocked on the §0.1 target reconciliation.)*

| ID | Change | Mechanism after move | Δ |
|---|---|---|---|
| **R2a** | `rules/finding-integrity.md` → `reference/finding-integrity.md` | 6 agent prompts already say `Read ~/.claude/rules/finding-integrity.md before starting`; update the path in those 6 lines. **Conditional.** | **−28** |
| **R2b** | `rules/codesight-fallback.md` → `reference/` | 5 agent prompts already read it explicitly; update paths. **Conditional.** | **−21** |
| **R2c** | `rules/test-files.md` → `reference/` | `ct-qa-reviewer.md:85`, `ct-spec-reviewer.md:74`, `SKILL.md:80` already point at it; plus `write-guard.py:643` blocks the violation outright. **Conditional.** | **−21** |
| **R2d** | `rules/dark-features.md` → `reference/` | `ct-implementer.md:189` already reads it. Add the same line to the auditors that perform reachability checks. **Conditional.** | **−19** |
| **R2e** | `rules/mcp-resilience.md` → `reference/` | **Precondition:** only `ct-simplify-auditor.md` currently references it. Add a literal `Read ~/.claude/reference/mcp-resilience.md` line to the remaining agent prompts *before* the move. **Conditional after precondition; do NOT move first.** | **−21** |
| | **Group A subtotal** | | **−110** |

### Group B — deletions (already enforced or dead)

| ID | Change | Justification | Δ |
|---|---|---|---|
| **R3** | Delete `rules/config-files.md` entirely | Zero readers. `:14` = `git-safety-guard.py:990` (blocks). `:15-17` unenforced style prefs with no consumer. `:18` duplicates `CLAUDE.md:174`. | **−18** |
| **R4** | `CLAUDE.md:141-158` + `:165` → delete | Blocked at `write-guard.py:643`/`:1054` with a `# mock-ok:` hatch; canonical text survives in `reference/test-files.md`. | **−19** |
| **R5** | `CLAUDE.md:178-183` (6 hard-blocked NEVERs) → 1 pointer line | Each is a fail-closed block: `git-safety-guard.py:976`, `:990`, `:1012`; `write-guard.py:1048`, `:1054`. Prose restating a block buys nothing and costs budget. Advisory-backed entries (`:187`, `:188`) are **kept** — advisory ≠ enforced. | **−5** |
| | **Group B subtotal** | | **−42** |

### Group C — extractions out of `CLAUDE.md`

| ID | Change | Loading mechanism (conditional?) | Δ |
|---|---|---|---|
| **R1** | `CLAUDE.md:15-59` Engram CLI → `agents/reference/engram-cli.md`, leave a 2-line pointer | Same pattern as `agents/reference/harness-engineer-reference.md` (verified absent from this system prompt). Read only when an agent needs engram syntax. **Conditional.** | **−44** |
| **R6** | `CLAUDE.md:125-139` model routing → `phases/model-routing.md`, remove entirely from CLAUDE.md | `phases/*.md` are read on demand by `SKILL.md` and `phases/execution.md` during dispatch. The section already declares itself *not for the always-loaded reader*. **Conditional.** | **−15** |
| **R7** | `CLAUDE.md:190-210` skill-suggestion table → data file consumed by the existing `prompt-dispatcher.py` rule surface, 2-line pointer retained | `hooks/prompt-dispatcher.py` already runs on every `UserPromptSubmit` and already injects. Carrying the table as **data** in an existing injector is exactly what PR #95's own rule 2 prescribes and what GP#11 requires. **NOT a new hook.** Conditional on prompt content. | **−19** |
| **R9** | `CLAUDE.md:224-227` UI/UX + `:184`, `:185`, `:167` (TS `any`, empty catch, naming) → `~/.claude/code-style.md` | `code-style.md` is already dispatched to agents on Python/TS/Angular/JS/HTML/SCSS work per `CLAUDE.md:214` and is verified absent from this system prompt. **Conditional on language.** | **−7** |
| **R10** | `CLAUDE.md:233-238` Obsidian vault → the `/save` skill | Skill files load only when the skill is invoked. **Conditional.** | **−6** |
| **R11** | `CLAUDE.md:229-231` hook deployment → 1 line | Order is already enforced by construction in `scripts/deploy.sh` (hooks at `:36`, settings at `:116`). Residual risk is hand-editing `settings.json`; 1 line covers it. | **−2** |
| | **Group C subtotal** | | **−93** |

### Group D — compressions (stay always-loaded, shrink)

| ID | Change | Δ |
|---|---|---|
| **R8** | `CLAUDE.md:61-67` cross-project memory → 3 lines; drop ContextKeep (C6) | **−4** |
| **R12** | `CLAUDE.md:98-104` handoff triggers → 2 lines folded into `:106-110` (see §6c) | **−5** |
| **R13** | `rules/scan-finding-completeness.md` 29 → 12: strip frontmatter `:1-4`, move `:22-23` + `:25-29` to `reference/` | **−17** |
| **R14** | `rules/no-known-broken.md` 15 → 8: strip frontmatter `:1-4`, drop `## Why` `:13-15` | **−7** |
| **R15** | `rules/defensive-simplify-guard.md` 16 → 10: strip frontmatter `:1-4`, drop `## Why` `:14-16` | **−6** |
| **R16** | `rules/hook-bypass.md` 19 → 14: strip frontmatter `:1-4` and deploy comment `:7` | **−5** |
| | **Group D subtotal** | | **−44** |

### Group E — additions

| ID | Change | Δ |
|---|---|---|
| **R17** | Land **Root Cause Over Symptom** in `config/CLAUDE.md` (see §6a) | **+6** |
| **R18** | Correct `exemption-override.md:5` path to `~/.claude/skills/coding-team/phases/named-rationalizations.md` (C7) | **0** |
| **R19** | Add always-loaded-cost marker to each surviving `rules/*.md` (F5) | **+6** |
| | **Group E subtotal** | | **+12** |

### Arithmetic

```
Current always-loaded (at audit)                     464
  Group A  relocations rules/ -> reference/         -110   [LANDED 2026-07-26, PR #123]
  Group B  deletions (enforced / dead)               -42
  Group C  extractions out of CLAUDE.md              -93
  Group D  compressions                              -44
  Group E  additions (incl. Root Cause rule)         +12
                                                    -----
Projected always-loaded                              187
```

***(Corrected 2026-07-27: this column previously printed 163 as the total. It sums
to 187. See §0.1 — and read the Final-state note below, which is where the 163
came from.)***

**Final state (as estimated at audit):** `config/CLAUDE.md` ≈ 100 lines · `~/.claude/rules/` ≈ 63 lines across 6 files (`hook-bypass` 14, `text-discipline` 14, `scan-finding-completeness` 12, `defensive-simplify-guard` 10, `no-known-broken` 8, `exemption-override` 5).

**⚠ The two methods disagree by 24 lines, and this is the crux.** `100 + 63 = 163`
is a **bottom-up** estimate of the end state. The column above is **top-down**
subtraction and lands at **187**. Reconciling from today's measured 354:

- Bottom-up demands **−191** of remaining reduction (CLAUDE.md 238→100 is −138; rules 116→63 is −53).
- Groups B + C + D + E enumerate only **−167**.
- **24 lines of reduction are therefore missing from the group breakdown** — the enumeration is incomplete relative to its own target, not merely mis-added.

**So the honest reading is: −167 is what this audit actually specifies, landing at
187 / 200 — 13 lines of headroom, not 37.** Reaching 163 requires finding 24 more
lines of reduction that no group currently names. Either extend the groups to cover
them or restate the target as 187. **And counting the unmeasured `MEMORY.md` (65
lines, §0.1 item 3), even 163 would leave the true surface at ~228 — still over
threshold.** F1 has landed and makes the measured portion observable; F2 must land
LAST, after the reductions.

---

## 6. Verdicts on the three named items

### 6a — Root Cause Over Symptom: where it goes and what it displaces

**Placement:** a new top-level section in `config/CLAUDE.md`, immediately after `# Your Role` (`:1-11`) and before `# Claude Code Configuration` (`:13`). Rationale: it is a *decision-making* rule, not a workflow preference — it governs how every other rule's failures are handled, so it belongs adjacent to the identity block, at the position of highest attention. It must NOT go in `rules/` (§1.1: same always-loaded cost, worse discoverability) and must NOT go on-demand (it applies to every fix, so no trigger can gate it).

Use the drafted text at `docs/handoff/2026-07-24-write-guard-allowlist-and-claudemd-audit.md:19` **verbatim** — it is already reviewed. As a heading + blank + paragraph + blank it costs **6 lines**.

**What it displaces — required, and specified:**

> **R1 alone (Engram CLI reference, `CLAUDE.md:15-59`, −44 lines) displaces it 7.3x over.**

This is the correct displacement pair for three reasons: (1) the Engram block is the single largest contiguous non-behavioral block in the file — 45 lines of command syntax with zero standing-rule content; (2) it is *reference*, and the Root Cause rule is *policy*, so the swap raises the file's policy density, which is the mechanism by which MANDATORY labels regain their binding; (3) it has a proven on-demand destination (`agents/reference/`, §1.2). Land R1 in the same change as R17. Net effect on the always-loaded surface: **−38 lines.**

This ordering also satisfies the rule's own content: landing a policy without displacement would be adding to a saturated surface — treating the symptom (this rule is being violated) by adding text, while the root cause (nothing binds at 464 lines) stays in place.

### 6b — PR #95 verdict: **3. Rework** (close in favor of the consolidated rule surface)

**Correction to the PR's own premise first.** The PR body states the file is a dark feature because "nothing injects the file at runtime, so `always-on` is a promise the harness does not keep." **That is backwards.** `scripts/deploy.sh:93-96` copies every `rules/*.md` (except `README.md`) into `~/.claude/rules/`, and `~/.claude/rules/*.md` loads unconditionally into every session and every subagent (§1.1). On merge + deploy, `interaction-mandatory.md` becomes **fully always-on** — the `scope: always-on` frontmatter is inert but irrelevant, because the directory does the work. It is not a dark feature; it is **+22 lines of unmetered always-loaded surface** (21 in the new file, +1 in `CLAUDE.md`) landing on a surface already at 2.32x threshold.

**Substance:** rule 1 (number either/or choices) is a **near-verbatim duplicate** of `config/CLAUDE.md:71`, which already carries the strongest language in the entire file — *"Standing global rule, every project, every time. I have asked for this repeatedly; do not make me ask again."* The operator has still had to repeat it.

That is the single most important datum in this audit. **A rule that is already always-loaded, already maximally emphatic, and still violated will not be fixed by adding a second always-loaded copy.** The failure is not that the rule is absent; it is that at 464 lines nothing binds. Merging #95 as-is adds 22 lines to the cause of the failure and calls it the fix. It is the same move as 6c, and the same move the Root Cause rule prohibits.

Rule 2 (don't default to hooks; consolidate) is genuinely new, genuinely valuable, and — notably — **this audit independently arrived at it** (zero new hooks proposed; R7 routes through the existing `prompt-dispatcher.py`; F1/F2/F3 all widen existing hooks). It deserves to survive.

**Options considered:**
1. **Merge as-is** — rejected. +22 lines to a 2.32x-saturated surface, with a duplicate rule, on a false premise about its own cost.
2. **Merge with wiring** — rejected. There is nothing to wire; it is already wired by `deploy.sh:93`. "Wiring" would only add a *second* delivery path and double the cost.
3. **Rework** — **recommended.** Close #95. Re-land rule 2 as ~4 compressed lines inside the surviving `config/CLAUDE.md` (it is a harness-design principle, adjacent to Hook Deployment at `:229`). Drop rule 1 entirely — `CLAUDE.md:71` already says it; the fix for its violation is the reduction (−277 as enumerated; see §0.1), not a duplicate. Net: **+4 instead of +22**, and the numbered-options rule gets a real fix (a file where it can be seen) rather than a second copy.
4. **Close outright** — rejected; rule 2 is worth keeping.

**Sequencing:** rework should land *after* Group A–D, so rule 2 arrives on a reduced surface rather than a 464-line one. *(The "157-line surface" this line originally named derived from the withdrawn 163 target; per §0.1 the enumerated groups land at 187, so the arrival surface is ~183 before rule 2's +4. Sequencing is unaffected.)*

### 6c — `config/CLAUDE.md:98-104` (PR #119, `6164e43`): **extract and compress**

Verified: `6164e43` (2026-07-26, *"docs: require an unprompted handoff before recommending a session restart"*) took `config/CLAUDE.md` from **226 → 238**. It is not exempt for being recent, and it is not exempt for being the operator's.

**It closed a real defect** — a session recommended a restart with no handoff and queue state was lost. The defect is real and the rule content is correct. That is not in dispute.

**But the block as written is 7 lines to carry roughly 2 lines of new information:**

- `:101` *"Context reaches 80% (compaction imminent)"* — **verbatim duplicate** of `:109` *"At 80% context, compaction is imminent — write a handoff note..."*, eight lines below, under a different heading. C3.
- `:102` *"The user says they are stopping, or asks to pause"* — a reasonable trigger, but it lands in a second list rather than the existing one at `:106-110`.
- `:100` (restart recommendation) and `:104` (the named rationalization *"they can ask for one if they want it"*) are the genuinely new, genuinely load-bearing content.
- `:98-99` are heading + preamble overhead created solely by opening a new subsection.

**Verdict: fold into the existing `### Compaction awareness` list at `:106-110` as two bullets** — one for the restart trigger, one for the named rationalization — and delete the `### Handoff triggers` heading, its preamble, and the duplicated 80% line. **Δ −5.** No rule content is lost; the named rationalization (the part that actually does the compliance work, per `memory/feedback-selective-fix-rationalization.md` and GP#3) is preserved verbatim.

**The meta-point, stated plainly as requested:** #119 is a well-intentioned change that made the compliance problem measurably worse. Adding 12 lines to a file that already fails to bind, to fix a case of that file failing to bind, is the symptom-masking move in its purest form — and it happened *while* the Root Cause rule was being held back pending this audit. The rule was right to be blocked; the same discipline should apply to #119's block.

---

## 7. Meta-observation

The harness is at **maturity Level 3** (custom middleware, observability, entropy management, agent-to-agent review) on `agents/*.md`, `phases/*.md`, and `skills/*/SKILL.md`, and at **Level 1** on the one surface that reaches every session. Fifteen hooks, four dispatchers, a fail-closed write guard, a 200-line blocking cap, a SessionStart health check, drift detection, and a promotion flywheel — all pointed away from `CLAUDE.md`.

The operator's complaint, *"you ignore all your standing rules,"* is **substantiated and correctly diagnosed**. The rules are not ignored by choice; at 464 lines they do not survive to the point of decision. `memory/feedback-context-saturation.md` predicted exactly this: past ~200 lines, MANDATORY labels stop binding. The harness wrote that lesson down, enforced it on three file classes, and exempted the one that mattered most.

Three second-order observations:

1. **The harness's de-duplication reflex has a blind spot.** Consolidating duplicated agent-prompt text into `rules/` felt like GP#11 Consolidate Before Adding. It was the opposite: it converted per-agent cost (paid once, by one agent, when dispatched) into global cost (paid by every session and every agent, always) — and did not even remove the per-agent read. `reference/` (F4) closes this permanently.

2. **Nothing in this audit needs a new hook.** Every structural fix widens a hook that already runs: `hook-health-check.py` (F1 and F3's measurement), `deploy-drift-check.py` (F3's deployed-only observability, still open), `write-guard.py` (F2), `prompt-dispatcher.py` (R7). The reliability budget in `memory/feedback-hooks-reliability-budget.md` is untouched, and the hook count stays at 15. This is what PR #95's own rule 2 asks for, arrived at independently.

3. **The strongest available evidence that always-loaded prose fails is already in the file.** `CLAUDE.md:71` is the most emphatic sentence in the harness — and the operator has had to repeat it enough times that a PR exists to state it a second time. If maximal emphasis at 464 lines does not bind, no amount of additional emphasis will. The only remaining lever is subtraction. That is what this audit recommends: **−277 lines as enumerated** (§0.1 — the original −301 assumed 24 lines of reduction the groups never name), then measurement (F1, **landed 2026-07-27**) and enforcement (F2) so it stays there.

---

## Appendix — Degradations during this audit

- **codesight:** `mcp__codesight__query` (`search-text`, `MAX_INSTRUCTION_LINES`) returned `result_count: 0` against repo `cmillstead/coding-team` with `files_searched: 42`. The symbol demonstrably exists at `hooks/hook-health-check.py:196` region (`if line_count > 200`). Index is mispointed/stale for this repo. Per `rules/codesight-fallback.md`: **one call, no retry**, degraded to Grep/Read. All underlying checks were performed with Grep/Read — none skipped.
- **engram:** CLI reachable but running without `sqlite-vec` (vector search degraded); the MCP equivalent responded with vector search available but returned **no node relevant to context saturation or instruction-file length** (top score 0.42, all hits about codesight/axon). No applicable KB pattern retrieved. Audit proceeded from `agents/reference/harness-engineer-reference.md`, `~/.claude/golden-principles.md`, and the `memory/feedback-*.md` corpus.
- **No other blind spots.** Every one of the 12 rules files *present at audit time* was read at its real path (Group A has since relocated 5, leaving **7**). Every referenced path in §4 was existence-checked by command.

---

## Appendix B — Decision predictions (for verify-mode adjudication)

`harness decisions --log` is unavailable on this machine (`which harness` → not found), so the
required per-fix predictions are recorded here. Adjudicate against the next `harness-map`
sidecar and a re-run of this audit's line arithmetic.

| Fix | Prediction (measurable) |
|---|---|
| **F1** add `check_always_loaded_surface()` to `hook-health-check.py` | Next SessionStart emits an **always-loaded surface** warning (a new aggregate check, distinct from the unchanged per-file instruction-length check) naming `~/.claude/CLAUDE.md` (238) and `~/.claude/rules/*.md` (116 across 7 files), total 354. Before: 0 warnings on these paths. After the Group B/C/D reductions: 0 warnings again, because the total drops under 200. *(Row corrected 2026-07-26 — the original predicted an instruction-length warning naming `config/CLAUDE.md` and a 226-line rules aggregate; the implemented fix measures the DEPLOYED paths and the rules total is 116 post-Phase-1.)* |
| **F2** widen `write-guard.py:767` `SKILL_MD_PATTERN` | An Edit/Write that would push `config/CLAUDE.md` over 200 lines returns `decision: block`. Regression check: edits that keep it ≤200 still pass. |
| **F3** two-way `deploy-drift-check.py` | **SUPERSEDED — see F3 (b).** The original prediction assumed the 5 parent-owned files would be moved into this repo; that prescription was retracted, so `~/.claude/rules/` keeps 2 symlinks + 5 regular files and the predicted "0 regular files" end state is unreachable. Replacement prediction, split by half: **(measurement, LANDED 2026-07-26)** `check_always_loaded_surface()` reports 354 today and 0 warnings once the reductions land — it spans both owners, so no ownership decision is required. **(observability, STILL OPEN)** if `deploy-drift-check.py` gains a deployed-only direction, its first run reports exactly 5 *foreign* (parent-owned) files, labelled as foreign rather than as drift. |
| **R2a-e** relocations to `reference/` | `wc -l ~/.claude/rules/*.md` drops from 226 to ~116 immediately after the move, and the 11 agent-prompt `Read` lines resolve to existing paths (`test -f` on each). No auditor reports BLOCKED for a missing protocol file in the following pipeline run. |
| **R1 + R17** Engram-out / Root-Cause-in | `wc -l config/CLAUDE.md` goes 238 → 200 in a single change (−44 +6). The Root Cause text matches `docs/handoff/2026-07-24-...:19` verbatim. |
| **R3-R16** full remediation | ~~`wc -l config/CLAUDE.md` ≈ 100; `~/.claude/rules/*.md` total ≈ 63; combined **163**~~ **Prediction revised 2026-07-27 (§0.1):** the enumerated groups deliver −167 from today's 354, so the falsifiable prediction is **combined ≈ 187**, and F1's aggregate check reports **zero warnings only if the target is 187 or lower AND `MEMORY.md` stays out of the measurement**. At 187 measured the check goes quiet; counting `MEMORY.md`'s 65 lines the true surface is ~251 and a check that measured it would still warn. **Do not score this prediction against 163** — that figure was a bottom-up estimate no group breakdown supports. |
| **6b** PR #95 reworked | PR #95 closed. Rule 2 lands as ≤4 lines; `grep -c "Number your options" config/CLAUDE.md` stays **1** (no duplicate). `rules/interaction-mandatory.md` does not exist. |
| **6c** `:98-104` folded | `### Handoff triggers` heading gone; the restart trigger and the `"they can ask for one"` rationalization both still present (grep both); the 80% trigger appears **once** (currently twice, `:101` and `:109`). |
| **Behavioral outcome** (the real test) | After the surface drops below 200, the operator does not need to restate the numbered-options rule (`CLAUDE.md:71`) again within the next 10 sessions. If they do, saturation was not the sole cause and the diagnosis needs revisiting. |
