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
