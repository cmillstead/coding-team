# Handoff — write-guard plan-scoped allowlist, Tasks 1–2 LANDED (2026-07-26)

Successor to `2026-07-25-write-guard-reachability-implementation.md` (that plan is COMPLETE;
do not reopen it). This covers the allowlist plan, `docs/plans/2026-07-24-write-guard-plan-allowlist.md`.

**Branch:** `fix/write-guard-plan-allowlist` · **Tip:** `e970cbb`
**Baseline:** `env -u WRITE_GUARD_ALLOW_INSTRUCTION_EDIT -u CODING_TEAM_MAIN_ROOT -u CODING_TEAM_TEST_SEAM python3 -m pytest hooks/tests/ --ignore=hooks/tests/test_prompt_dispatcher.py -q`
→ **1025 passed, 0 failed, 9 skipped**. `python3 -m ruff check .` clean. Live hook healthy.
All verified by the orchestrator, not taken from an agent report.

**Working tree:** clean except two PRE-EXISTING, not-ours files — `.claude/settings.local.json`
(modified) and an untracked file under `skills/second-opinion/codex-learnings.d/`. Never stage either.

---

## READ THIS FIRST — why you were relaunched

This session carried `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1`. Tasks 1–2 were unaffected (no plan
armed → gate dormant), but **Tasks 3–5 dogfood the allowlist, and that flag short-circuits the exact
branch they test.** Before doing anything:

```
echo "[${WRITE_GUARD_ALLOW_INSTRUCTION_EDIT}]"     # MUST print []
```

If it prints `[1]`, you are still in a pre-`f6c70b9` session. Relaunch — the flag is injected at
session start and cannot be cleared from inside. Every "allowed" result you get with it set is
meaningless.

---

## What landed

| Commit | Content |
|---|---|
| `b20a374` | **Task 1** — allowlist reader in `_lib/active_plan.py` |
| `a4fc422` | duplicate-key error now names the offending plan file |
| `e970cbb` | **Task 2** — allowlist wired into `check_phase5()` |

Public surface added to `hooks/_lib/active_plan.py`:
- `INSTRUCTION_ALLOWLIST_KEY = "instruction_files"`
- `MalformedInstructionAllowlistError(RuntimeError)` — callers MUST fail closed
- `read_instruction_allowlist(plan, root) -> frozenset[Path] | None`
- `_parse_frontmatter(text, preserve_case_keys=frozenset())` — opt-in case preservation; default
  unchanged. Also now raises `AmbiguousActivePlanError` on a duplicate key.

**Verified working end to end, scrubbed, by the orchestrator** (throwaway repo, armed plan declaring
`agents/declared.md`): declared file → allow; undeclared file → block naming the arming plan AND the
declared list. Control confirmed `hatch=[]` on both.

---

## Engineering decisions D1–D4 (recorded in the plan, `:117-186`)

- **D1** — the allowlist re-resolves the arming plan via the AUTHORITATIVE UNCACHED
  `find_active_plan()` on the instruction branch only. A cache hit can return plan A while the
  authoritative call raises `AmbiguousActivePlanError`; since the allowlist attaches per-file
  authority to the specific plan returned, that is an authorization bug, not a staleness quirk.
  Does NOT close the general stale-POSITIVE hole — still open, still recorded.
  **Severity note:** the window is narrower than the plan originally implied. `_compute_signature()`
  covers every `*.md` with its `st_mtime_ns`, so an ordinary status flip busts the cache and forces a
  rescan. Reaching the stale hit needs an mtime-preserving change (restore, `touch -r`, hand-written
  cache entry). D1 is cheap insurance, not a load-bearing fix.
- **D2** — declared entries resolve against `worktree_root` (the edited file's own worktree), NOT
  `plan_root` (which `--git-common-dir` pins to the main checkout). Without this a correctly-declared
  file edited from a linked worktree is falsely BLOCKED.
- **D3** — a duplicate frontmatter key is a HARD ERROR. Verified safe: zero existing plans have one.
- **D4** — every `_assert_blocked` call site asserts its gate's own reason substring plus a universal
  `HOOK CRASH` exclusion.

---

## Bootstrap for Tasks 3–5 — exact order

1. Confirm `echo "[${WRITE_GUARD_ALLOW_INSTRUCTION_EDIT}]"` prints `[]`.
2. Run `scripts/deploy.sh` so the symlinked hook carries the new reader.
3. **Then** add this plan's own declaration to its frontmatter — the canonical 7-file set:
   ```
   instruction_files: hooks/_lib/active_plan.py, hooks/write-guard.py, hooks/tests/test_active_plan.py, hooks/tests/test_write_guard.py, SKILL.md, phases/execution.md, phases/named-rationalizations.md
   ```
4. **Then** flip `status: planned` → `status: in-progress`.
5. Verify the handoff: an edit to `hooks/write-guard.py` must be ALLOWED, an edit to an undeclared
   instruction file (e.g. `agents/ct-qa-reviewer.md`) must be BLOCKED. If the undeclared edit is
   allowed, the wiring is wrong or the env var is still set — stop and fix before Task 3.

Tasks 3–5 then run THROUGH the allowlist. That is deliberate dogfooding: if the feature is broken,
Task 3 cannot proceed, and that failure is the signal.

---

## GAP — read before flipping

`phases/task-weight.md:35` is now mildly stale: it says the write-guard "always-delegates"
instruction files, which stopped being unconditional the moment a declared file is allowed. The
risk-tiering conclusion it supports (Medium+) is unaffected, so this is accuracy drift, not a
correctness break.

**But it is NOT in Task 4's scope and NOT in the 7-file declaration above.** If you decide to fix it,
add it to the declaration BEFORE flipping, or the gate you just built will block you. If you decide
not to fix it, say so explicitly rather than leaving it to be rediscovered.

Same check applies generally: **cross-check the declaration against every file Tasks 3–5 will touch
before flipping.** A missing entry wedges the task that needs it.

Also noted by the Task 2 implementer and correctly left alone as out of its scope:
`phases/execution.md` and `phases/named-rationalizations.md` still describe the pre-allowlist
"blocks ALL instruction-file edits" behavior. Both ARE declared, and Task 4 owns them.

---

## Task 3 is fully specified — including two locks that did not exist before

Task 3's `Step 1a` (`~:1359`) carries fully-coded specs for both:
- `test_declared_file_allowed_from_linked_worktree` (D2) — must pass `use_root_seam=False` or it
  passes vacuously.
- `test_stale_cache_hit_does_not_launder_a_misidentified_plan` (D1) — **cannot be built by ordinary
  means.** An ordinary flip of a second plan busts the cache signature and forces a miss. It must be
  built through the `ACTIVE_PLAN_CACHE_FILE` seam with a hand-written entry. The spec explains this;
  do not "simplify" it into an ordinary fixture, which silently reverts the coverage.

---

## Non-negotiables (each cost a round to learn)

1. **Editing `hooks/write-guard.py` or `hooks/_lib/*` can wedge the session editing it.** The live
   hook imports them; a crash blocks ALL Edit/Write for every agent at once, and
   `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT` cannot recover it (read after the crash point). One
   self-consistent edit at a time; after each, probe the LIVE hook —
   `echo '{"tool_name":"Edit","tool_input":{"file_path":"<repo>/README.md","new_string":"x"}}' | python3 hooks/write-guard.py`
   (empty = healthy). **Import alone is insufficient** — it passed while wedged. If wedged: STOP and
   report; do NOT repair via Bash.
2. **Scrub the override on EVERY gate probe**, and pair it with a control that must block. An
   unscrubbed *allow* is worthless evidence; an unscrubbed *block* still counts.
3. Every block assertion excludes `HOOK CRASH` and requires a gate-specific reason. A *conditional*
   assertion block is a vacuity hole.
4. Explicit paths on every commit. Never `git add -A`.
5. `docs/plans/` is gitignored — nothing there is ever staged or committed.

---

## Tooling issue worth fixing

codesight's index is mispointed for this repo: it rejects the path as outside its trusted
`/Users/cevin/src/` prefix, and its "coding-team" indexed repo returns ZERO results for test classes
that demonstrably exist. Agents fall back to Grep/Read correctly, so nothing was lost — but a stale
index that returns *empty* rather than *erroring* reads as "no callers found" and gets trusted.
Re-point it before an audit leans on it.

---

## After this plan

Queued: #1 spec-silence meta-rule (paused, its Codex plan gate never ran), #3 CLAUDE.md audit
Batch 1, #4 `commands/` not in `deploy.sh` (stale `/build` + 5 undeployed commands).

Open decision, still unanswered: `docs/tickets/2026-07-25-self-modifying-hook-no-safe-edit-path.md`
lists four options and picks none. Needs a human call.
