# Handoff — 2026-07-24 — write-guard allowlist, spec-silence (paused), CLAUDE.md audit

Session started on `main` in `~/.claude/skills/coding-team`. Three workstreams, two paused/pending.
Currently on branch `fix/write-guard-plan-allowlist`. Only uncommitted file: `.claude/settings.local.json` (pre-existing, unrelated).
No commits on any branch this session — all work so far is plans and audits.

---

## Operator directives issued this session (standing)

1. **Root cause over symptom.** Verbatim: *"I never want to see a fix like ff866aa again. we solve problems by dealing with the underlying issue, not by masking the symptoms."* Rule text drafted (below), NOT yet written anywhere — deliberately blocked on the CLAUDE.md audit.
2. **Compliance complaint, substantiated.** Verbatim: *"you ignore all your standing rules."* Confirmed violations this session: the "don't summarize what you just did at the end of responses" rule (violated repeatedly via end-of-turn status blocks) and the future-tense narration ban in `~/.claude/rules/text-discipline.md`. Do not repeat these.
3. Merge decision: local `git merge --no-ff` into main stays BLOCKED. PR-merge remains the only path. No work required.

### Rule text to land (pending audit outcome)

> **Root Cause Over Symptom.** Fix the underlying problem. Never ship a change whose effect is to make a problem *less visible* while leaving it in place. **A blocked mechanism is not a blocked problem** — the dangerous case is diagnosing the root cause correctly, finding the obvious fix impossible, and then treating the *problem* as unfixable. When the first mechanism fails, find a second; do not improve the error message and move on. Symptom-masking includes: rewriting an error message so a broken path reads as intended, adding an override/flag/env var to bypass, widening a permission, catching an exception without addressing what raised it, documenting a limitation instead of removing it. If you must ship a mitigation, say plainly that it is one, record the unresolved root cause and the constraint that blocked it, and note what would have to change to fix it properly. Rationalizations: "the platform doesn't support it" (it blocks ONE mechanism — find another); "this was investigated and found impossible" (check what was actually ruled out — usually one approach, not the goal); "the fix makes the failure clear to the user" (clarity about a defect is not repair); "it's the sanctioned escape hatch" (an escape hatch used routinely is a design defect).

---

## Workstream 1 — write-guard plan-scoped allowlist (ACTIVE, highest priority)

Branch `fix/write-guard-plan-allowlist`. Plan: `docs/plans/2026-07-24-write-guard-plan-allowlist.md` (64.7K, `status: planned`, 5 tasks, tier **Medium**).

### Why

`hooks/write-guard.py` blocks edits to behavioral instruction files whenever a plan has `status: in-progress`. Commit `ff866aa` (PR #59) diagnosed defect D1 "Unsatisfiable remediation": the harness policy says instruction edits MUST be delegated to the Agent tool, but the hook is a process-global `PreToolUse` hook that fires identically inside subagents, so the prescribed route loops back into the block. That commit fixed the *error message* and made `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1` — a session-wide disarm — the routine route. This is the `ff866aa` the operator never wants to see repeated.

### The fix

Active plan declares `instruction_files: agents/a.md, agents/b.md` in frontmatter; guard authorizes exactly those, blocks all others. Strictly tighter than the env var (per-file and plan-reviewed vs. session-wide blanket disarm). Needs no subagent detection.

### Settled — do NOT re-open

**Subagent detection is permanently unavailable.** Researched this session by a Claude Code hooks specialist: `PreToolUse` exposes only `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`; `session_id` and `transcript_path` are SHARED between parent and subagents; the upstream request to add `agent_id`/`agent_type` to PreToolUse was closed as NOT PLANNED; `SubagentStart`/`SubagentStop` carry identity but fire at spawn/exit, not per tool call. Independently corroborated by `hooks/write-guard.py:102-111`. **Do not propose "detect the subagent instead" — it is not implementable.** (Upstream issue numbers were cited by the specialist but NOT independently verified; do not repeat them as fact.)

### Verified facts (checked by command — trust these)

- `SKILL.md` is **198** lines; 200-line cap enforced by `check_skill_line_cap` at `hooks/write-guard.py:506`. **2 lines of headroom** — the doc task must rewrite in place, never append, or it blocks its own plan.
- `check_path_safety` at `hooks/write-guard.py:719` flags `.startswith()` on path vars in `.py` writes (case study #35) — a substring implementation would trip the repo's own hook.
- `_parse_frontmatter()` (`hooks/_lib/active_plan.py:50-78`) handles ONLY flat `key: value` and **lowercases every value** (`:77`). A YAML list will not parse; unmodified, it would corrupt `SKILL.md`/`CLAUDE.md` entries to `skill.md`/`claude.md`. Plan adds opt-in `preserve_case_keys`.
- `hooks/tests/conftest.py:120-142` scrubs `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT` for the whole test session — new tests inherit it.
- `~/.claude/hooks/write-guard.py` is a relative symlink to repo source. Edit SOURCE then `bash scripts/deploy.sh`. Never hand-edit deployed.
- `docs/plans/` is gitignored (`.gitignore:2`) → plans survive branch switches, and the allowlist has no git audit trail (threat-model note: process discipline, NOT a security boundary — must not be oversold).
- `find_active_plan()` fails closed if MORE THAN ONE plan claims `status: in-progress`. Two plans now exist; only one may ever be armed.

### In flight when compacted

- `wg-reviewer` (Coding Team Plan Doc Reviewer) — reviewing the plan. Priorities: fail-closed completeness, path-matching soundness, `_parse_frontmatter` regression risk, back-compat proof, SKILL.md 2-line headroom, deploy/declare ordering.
- `wg-codex` (Codex gate, Medium tier REQUIRED) — told it MUST prove execution (command line, tee'd path, byte size), because a prior agent silently never dispatched.

### Next steps

1. Collect both gate results; reject false findings by command (see Discipline below).
2. Apply accepted findings, then implement Tasks 1-5.
3. Task 5 declares `instruction_files: agents/ct-spec-reviewer.md, agents/ct-qa-reviewer.md` in the spec-silence plan — the end-to-end proof.
4. Full hook test suite + ruff must be green. `bash scripts/deploy.sh` is mandatory.

---

## Workstream 2 — spec-silence meta-rule (PAUSED at end of Phase 4)

Branch `feat/spec-silence-meta-rule` (**no commits** — Phase 5 never ran). Plan: `docs/plans/2026-07-24-spec-silence-meta-rule.md` (39.2K, `status: planned`, 4 tasks, tier Medium). Untracked/gitignored, survives branch switches — verified intact after the switch.

### What it does

New `rules/spec-silence.md` + symlink into `~/.claude/rules/` via `scripts/deploy.sh`, referenced by a one-line pointer from exactly TWO agents: `agents/ct-spec-reviewer.md` (Misunderstandings group, ~line 107) and `agents/ct-qa-reviewer.md` (`## Named Rationalizations`, ~line 123). The other seven `ct-*.md` are deliberately OUT of edit scope (Task 4 Step 5 greps them report-only).

Rule content: before filing "code violates invariant X", check whether the spec PINS X. If silent/ambiguous → still file, retitled **SPEC-AMENDMENT CANDIDATE**. Three suppression routes closed across two review rounds: **COUNT** (still filed), **SEVERITY** (unchanged by retitling), **DISPOSITION** (not advisory; still blocks). Rule body is 46 lines against a `≤ 50` assertion.

### Outstanding

**Codex plan gate NEVER RAN.** The `codex-gate` agent idled without dispatching (verified: nothing written to `/tmp/second-opinion-*` or scratchpad in 90 min) and was stopped. Medium tier REQUIRES it — re-run from scratch on resume.

Reusable pre-flight (mode=plan, live count 31):
- applicable (23): C4 C10 C12 C13 C14 C15 C16 C18 C19 C20 C21 C22 C25 C26 C27 P1 P2 P3 P4 P30 P32 P33 P34
- dismissed (8): scope-mismatch C2 C3 C5 C23 C24; no-signal C11 C17 P31
- battery: path-equality 0, select-threading 0, metric-aggregate 0 (absent); concurrency-lock 14, command-grammar 31 (fire, both over-matches on prose)

### Resume condition

After the write-guard fix lands: `instruction_files` is added to this plan's frontmatter (done by the fix's own Task 5), flip `status: in-progress`, run Phase 5 **with no env var and no session relaunch**. Anchors verified verbatim against live files; both target agents stay under 200 lines (152→153, 155→156).

---

## Workstream 3 — CLAUDE.md saturation audit (RUNNING)

`claudemd-audit` (Coding Team Harness Engineer) auditing `config/CLAUDE.md`.

**Finding that triggered it:** `config/CLAUDE.md` is **226 lines**, symlinked to `~/.claude/CLAUDE.md` and therefore always loaded in every session. That is past the 200-line threshold `hooks/hook-health-check.py` enforces and past the point `feedback-context-saturation` / case study #24 record as where MANDATORY labels stop binding. This is the root cause of "you ignore all your standing rules" — so the fix is to SHRINK and HARDEN, not to add rule N+1.

Audit asks: enumerate every rule; classify each as ALREADY-ENFORCED (cite hook file:line) / MECHANIZABLE (propose hook, applying the reliability budget — operator deliberately cut 28 hooks to 9) / NOT-MECHANIZABLE-ESSENTIAL / SITUATIONAL (extract to on-demand); report line arithmetic; flag contradictions and dead references; and say where the new root-cause rule belongs and what it displaces.

**Decision made:** do not add the root-cause rule until this audit returns. Adding line 227 to a saturated file is itself the symptom-masking move the rule prohibits.

---

## Discipline notes for the next session (earned the hard way)

**Verify state claims by command.** Six findings from agents this session were FALSE, and every single one was an unverified claim about working-tree or environment state — current branch, file line counts, file existence, BSD grep behavior — while the same agents' file-CONTENT analysis was consistently accurate and valuable. Reject the false premise, keep the rest, tell the agent which is which. Saved as `memory/feedback-unverified-premise-findings.md`.

I made this error too: claimed `hooks/write-guard.py` was untracked by git. Cause — an earlier `cd` into a subdirectory persisted in the shell, so `hooks/` and `.gitignore` resolved relative to the wrong directory. **The Bash tool's working directory persists between calls.** Use absolute paths or re-`cd` to repo root.

**Agents finish work but often never send the report.** Four times this session (`planner`, `plan-reviewer-2`, `cc-hooks-expert`, `wg-planner`). On an idle notification with no report: inspect the ARTIFACT first (the work is usually done), then ping asking them to re-send, and explicitly offer `Status: BLOCKED` as an honest alternative to reconstructing from memory. Do NOT re-dispatch a fresh agent — that discards completed work. Saved as `memory/feedback-agent-idle-without-report.md`.

**Guard state:** currently 0 plans with `status: in-progress`, so `write-guard.py` is dormant and hook/instruction edits are allowed. If a future session finds edits blocked, check for a stale `in-progress` plan before reaching for the env var.

---

## Plan review results — write-guard allowlist (received post-handoff)

`wg-reviewer` returned **Issues Found**: 7 findings (1 Critical, 2 High, 2 Medium, 2 Low). It ran NO shell
commands (no Bash tool in its dispatch), said so explicitly, and grounded every claim in file:line content.
No tree-state claims — nothing to reject as false premise. Treat these as sound.

### BLOCKING — must be fixed before implementation

**R1. Bootstrap deadlock — the plan blocks its own execution (Critical).**
All six files in the plan's File Structure table (`:85-91`) are gated by `is_instruction_file()`:
`hooks/_lib/active_plan.py`, `hooks/tests/test_active_plan.py`, `hooks/write-guard.py`,
`hooks/tests/test_write_guard.py` (`"hooks" in parts and suffix in (".py",".sh")`, `write-guard.py:92`);
`SKILL.md` (`BEHAVIORAL_INSTRUCTION_BASENAMES`, `:64`, `:84-85`); `phases/execution.md`
(`BEHAVIORAL_INSTRUCTION_DIRS`, `:65-72`, matched `:96-97`). The plan is `status: planned` with NO
`instruction_files` key. Flipping to `in-progress` at Phase 5 entry makes `check_phase5` (`:194-216`)
block Tasks 1-4. Self-declaration cannot rescue Tasks 1-2 — they run BEFORE the allowlist code exists,
so the old guard ignores the key.
FIX: explicit prerequisite — `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1` for Tasks 1-2 ONLY; once Task 2 lands
(hook live via symlink), add `instruction_files:` to THIS plan's own frontmatter covering all six files
and UNSET the env var so Tasks 3-5 dogfood the new mechanism. That is also a stronger E2E proof than the
current Task 5 Step 4.

**R2. New routing text is unsatisfiable for out-of-repo instruction files (High). REPRODUCES ff866aa's D1.**
`is_instruction_file()` gates by path SHAPE anywhere on disk — no repo-root constraint (`:75-99`) — but
`read_instruction_allowlist()` rejects absolute entries and anything escaping the repo root (plan `:374-391`).
So `~/.claude/CLAUDE.md`, `~/.claude/agents/*.md`, and instruction files in OTHER repos can never be
declared; the env var remains their only route — while the new block message labels declaration
**PREFERRED** (`:684-689`) and the SKILL.md row (`:1029`) states it unconditionally.
This is the same "unsatisfiable remediation" defect class as D1, which the plan itself cites at `:23`.
**EM DECISION REQUIRED** (operator directive: root cause over symptom — do NOT just scope the claim, that
is documenting a limitation):
  (a) Make out-of-repo instruction files declarable — permit entries resolving under a known harness root
      (`~/.claude`) in addition to the arming plan's repo. Threat model is process discipline, not an
      adversarial boundary, so a second known root is acceptable. PREFERRED — actually fixes it.
  (b) Scope the block message + SKILL.md claim to in-repo files only. Honest but leaves the gap = the
      symptom-masking move the operator just prohibited. Only if (a) proves unworkable.

### IMPORTANT

**R3. Task 1's import instruction is wrong; tests would fail at collection (High).**
Plan `:246` says to match the file's existing import style, but `hooks/tests/test_active_plan.py:13-20`
has NO module-level import of `_lib.active_plan` and never does `sys.path.insert` — it reaches the library
only via `run_python()` subprocess snippets (`:50-63`), which is incompatible with the new in-process calls.
Result: `ModuleNotFoundError: _lib` at collection, masked by Step 2's predicted `ImportError` (`:250-251`).
FIX: specify BOTH `sys.path.insert(0, str(HOOKS_DIR))` and explicit `from _lib.active_plan import ...`.
Precedent: `hooks/tests/test_write_guard.py:29-32`.

**R4. Failure-modes table claims coverage three tests do not provide (Medium).** Load-bearing, since that
table is the plan's fail-closed evidence.
- `:1160` repo-root-unresolvable — the `allowlist_repo` fixture (`:229-241`) always SETS
  `CODING_TEAM_MAIN_ROOT` and never unsets it; branch at plan `:359-364` is untested.
- `:1156` `test_declared_but_unreadable_plan_blocks` (`:926-943`) never reaches the reader's unreadable
  branch — `find_active_plan()` raises `AmbiguousActivePlanError` first (`active_plan.py:130-137`,
  handled `write-guard.py:175-184`). Passes for the wrong reason. (T1's `test_unreadable_plan_raises`
  does cover it.)
- `:1163` "unexpected exception → covered by bare-except" — nothing forces one. Untested.

**R5. Exception-type mismatch (Medium).** Reader catches only `OSError` (`:380-386`); matcher catches
`(OSError, ValueError)` (`:611-614`). `Path.resolve()` raises `ValueError` on an embedded NUL, which
survives `read_text(errors="replace")` and `_FRONTMATTER_KEY_RE`'s `(.*?)` (`active_plan.py:46`), so it
escapes as raw `ValueError`, contradicting the reader's docstring (`:332-335`). Still FAILS CLOSED via
`check_phase5`'s broad `except Exception` (`:648`), but the unit contract is wrong.
FIX: `except (OSError, ValueError)`.

### MINOR
**R6 (Low).** Dead code in `test_suffix_near_miss_not_authorized` (`:774-786`): `near` is created but never
asserted on; reads half-edited. Reasoning is correct (`is_instruction_file` keys off `path.suffix`).
**R7 (Low, advisory).** `except Exception` at `:648` conflicts with `~/.claude/code-style.md:6`, but is
load-bearing here (it is what turns R5's `ValueError` into a block). KEEP IT — state the deliberate
exception in the plan so a later auditor doesn't narrow it and reopen a fail-open path.

### Verified sound by the reviewer — do not re-audit
- Fail-closed: no input found that yields an ALLOW; only `return None` in new logic is the exact-match
  branch (`:658-661`). (Apart from R5's exception TYPE.)
- Path matching holds for `a.md.bak`, `evil/agents/a.md`, `agents/../agents/a.md`, absolute targets,
  trailing whitespace, duplicates. A declared DIRECTORY authorizes nothing (no wildcard leak). A symlink to
  a declared file resolves to it and is allowed — semantically correct. Case variation on APFS OVER-blocks
  (fail-closed direction).
- `preserve_case_keys` default is byte-identical to `active_plan.py:77`; the ONLY in-repo caller of that
  `_parse_frontmatter` is `find_active_plan` at `:139` (other grep hits are unrelated same-named local
  functions). No `find_active_plan()` regression.
- Back-compat IS proven by test (`test_no_key_blocks_every_instruction_edit`, `:539-554`), honestly flagged
  at `:577` as a regression lock rather than red-green.
- SKILL.md 198/200 headroom handled: Task 4's edits are 1→1 in place, table stays 2 rows, net 0.
- Test helpers verified: `_run(event, cwd, env)` (`test_write_guard.py:94-96`), `_write_plan(body=...)`
  (`:83-91`), `stat` already imported at `:18`.
- Stale-doc inventory complete: `SKILL.md:159`, `:179-180`, `:185`, `phases/execution.md:22` all carry the
  "go through the Agent tool" claim verbatim.

### Next action after compaction
Apply R1-R5 to the plan (R1 and R2 are blocking; R2 needs the EM decision above, defaulting to option (a)),
then re-review, then implement. `wg-codex` (Codex gate, REQUIRED at Medium) was still running.

---

## Round 2 — Codex gate returned, R1-R5 + Codex findings APPLIED (post-compaction)

`wg-codex` completed: 438K transcript at `scratchpad/wg-codex-r1.txt`. **VERDICT: REVISE**, ~6 P1 /
~12 P2 / ~4 P3. It ran for real this time (unlike the earlier silent `codex-gate` no-op).

### Cross-model agreement (highest confidence)
Codex independently found **R1's bootstrap deadlock**. Two models, two methods, same defect.

### Applied to the plan — all of R1-R5 plus every Codex P1

**Design changes (not patches):**
1. **Reader takes `root` as a parameter** instead of calling `_git_main_root()` a second time.
   `check_phase5` derives it as `active.resolve().parents[2]` — `find_active_plan()` only ever globs
   `<root>/docs/plans/*.md`, so that IS the root by construction. This single change killed four
   findings at once: the double-git-call P2, the "root is None → full hook ALLOWS" P1 fail-open, the
   "nonexistent root accepted" P1, AND the `allowlist_repo` fixture's `CODING_TEAM_MAIN_ROOT`
   env-mutation problem (R4's first half). No `git rev-parse` remains on this codepath.
2. **Empty entries now REJECT** rather than being filtered. `a.md,,b.md` was silently normalized into a
   valid declaration — a typo becoming an authorization.
3. **`_assert_silent_allow()` helper** replaces all six vacuous `if parsed is not None:` positive
   assertions. Codex's sharpest finding: an import-time crash also yields `parsed is None`, so those
   tests passed green against a completely broken hook. Now asserts rc==0, empty stdout, no traceback.
   All 13 `_run` sites changed from `_stderr, _rc` to captured `stderr, rc`.
4. **Bootstrap section added** (R1): env var for Tasks 1-2 only → deploy Task 2 → self-declare in this
   plan's own frontmatter → unset env var → flip `in-progress` → Tasks 3-5 dogfood the allowlist.
   Includes a verification gate at the handoff point.

**R2 — DECISION REVERSED, and this matters.** The pre-compaction default was "add `~/.claude` as a
second root." Investigation killed it: every `ct-*` agent, every coding-team rule, and
`~/.claude/CLAUDE.md` are **symlinks into this repo** (`~/.claude/CLAUDE.md` →
`skills/coding-team/config/CLAUDE.md`). The matcher `.resolve()`s both sides, so all of them are
ALREADY declarable as repo-relative paths. The only genuinely undeclarable gated files are
`~/.claude/agents/bt-*.md`, which belong to the brainstorming-team project — and editing those from a
coding-team session is already forbidden by session-directory discipline in `CLAUDE.md`. So the block
is CORRECT, not a limitation; a second root would have authorized what another rule forbids. The block
message now names the real remedy (restart in the owning repo). This is not ff866aa's D1: that
documented an *unreachable* route, this documents a *reachable* one.

**Plan-accuracy corrections** (Codex found ~8 of these — the plan asserted things about existing files
that were false):
- Task 1 import instruction (R3): `test_active_plan.py` has NO `_lib.active_plan` import and no
  `sys.path` setup — it uses subprocess + sentinel counters. Now specifies the `sys.path` block from
  `test_write_guard.py:29-32` explicitly.
- Failure-modes table rows claiming tests that were never written are now marked **MUST ADD** with
  named tests, plus a note that the table is a checklist, not a record.
- `test_declared_but_unreadable_plan_blocks` (R4 second half) passes for the wrong reason —
  `find_active_plan()` raises `AmbiguousActivePlanError` at `active_plan.py:133-137` before the reader
  runs. Verified by reading the source. Test kept, relabeled; the row now credits only T1's unit test.
- `except (OSError, ValueError)` on both resolve sites (R5) — NUL bytes raise `ValueError`.
- "audit trail" / "auditable" claims removed — they contradicted the plan's own Context Brief item 5
  (`docs/plans/` is gitignored).
- `test_agent_rule_refs.py` is NOT in the smoke job (`ci.yml:30`); it's gated by the full-suite job
  (`:61`). Verified by reading the workflow.
- Task 4's "complete set" of stale docs omitted `phases/named-rationalizations.md:21`. Added — but its
  ROUTING rule is deliberately retained; only the *sufficiency* implication is stale. Step 5's grep
  expectation changed from "no matches" to "exactly one match".
- Task 5 Step 4 split into **4a (reader check, honestly labeled NOT end-to-end)** and **4b (genuine
  E2E)** — the old step claimed "temporary flip and restore" while explicitly doing neither, and never
  invoked the hook. 4b now runs `write-guard.py` as a process in a disposable git repo and asserts
  declared→allow AND undeclared→block.
- `git add -A` → explicit paths (the tree carries unrelated `.claude/settings.local.json`).

### Recorded but deliberately NOT fixed here
Three **pre-existing** `is_instruction_file()` holes, now in the plan's "Known gaps" section per
`rules/finding-integrity.md`. They let a payload skip classification before any allowlist logic runs,
so they are orthogonal — neither blocked by nor fixed by this work:
1. Ungated symlink alias (`notes/x.txt` → `agents/X.md` classifies as non-instruction).
2. Case-insensitive APFS (`skills/demo/skill.md` == `SKILL.md` on disk, not in the basename set).
3. Frontmatter past the 4096-char window, and unterminated frontmatter, both silently disarm the gate.

Each needs its own plan. They widen scope from "who is authorized" to "what counts as an instruction
file" — a different review.

### Verified, not asserted
- All 11 `python` blocks + both heredocs parse (`ast.parse`, with dedent for the two fragments).
- Zero vacuous `if parsed is not None:` test sites remain (3 hits are the helper + its prose).
- `check_path_safety` will NOT fire on the new code — it uses `is_relative_to()`, which is in
  `PATH_SAFE_PATTERNS`.
- Plan is 1446 lines.

### Next action
Re-review the revised plan (it changed substantially — the reader signature change touches Tasks 1, 2
and 5), then implement starting from the Bootstrap section. Do NOT flip `status: in-progress` before
Task 2 is deployed.
