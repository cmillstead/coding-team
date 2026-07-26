# Handoff — unstarted work inventory (2026-07-26)

Written per the handoff-triggers rule added today (`config/CLAUDE.md:98-104`). Every
item below carries its **state**, **artifact path**, and **what resuming means** —
a bare list of names is not a handoff.

**Repo state at handoff:** `main` @ `0dbdb8e`, clean, deployed, 1039 passed / 9
skipped, `ruff check .` clean, live hook healthy. No plan is `status: in-progress`,
so `write-guard.py` is **dormant** — instruction edits are currently allowed. If a
future session finds them blocked, look for a stale `in-progress` plan before
reaching for `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`.

**Working tree carries two pre-existing not-ours files** — `.claude/settings.local.json`
(modified) and an untracked file under `skills/second-opinion/codex-learnings.d/`.
Never stage either.

**Shipped today (do not reopen):** PR #118 write-guard plan-scoped allowlist +
reachability arc; #119 handoff-triggers rule; #120 hook restart message. All merged.

---

## 1. Spec-silence meta-rule — PAUSED

- **Artifact:** `docs/plans/2026-07-24-spec-silence-meta-rule.md` (gitignored)
- **State:** 497 lines, `status: planned`, **31 task checkboxes, 0 checked** — fully
  planned, zero execution. Nothing was in flight; there is no partial work to recover.
- **Already done for it:** it now carries the first real allowlist declaration —
  `instruction_files: agents/ct-spec-reviewer.md, agents/ct-qa-reviewer.md`. Both
  paths verified to exist. It also creates `rules/spec-silence.md`, which
  `is_instruction_file()` does NOT gate, so that file needs no declaration.
- **Why it paused:** its Codex plan gate never ran. That is the only blocker.
- **Resume:** run the Codex plan gate on the plan; apply any findings; then flip
  `status: planned` → `in-progress` and execute the 31 tasks. Cross-check the
  declaration against every file the tasks touch BEFORE flipping — a missing entry
  wedges the task that needs it.

## 2. CLAUDE.md saturation audit — DISPATCHED, NEVER RETURNED

- **Artifact:** none. The agent (`claudemd-audit`, Coding Team Harness Engineer) was
  dispatched on 2026-07-24 and the session ended before it reported. **No findings
  document exists.** Scope is recorded at
  `docs/handoff/2026-07-24-write-guard-allowlist-and-claudemd-audit.md:86-98`.
- **Why it exists:** `config/CLAUDE.md` is symlinked to `~/.claude/CLAUDE.md` and
  therefore always loaded. At 226 lines it was already past the 200-line threshold
  `hooks/hook-health-check.py` enforces and past where `feedback-context-saturation`
  records that MANDATORY labels stop binding. The audit's framing: this is the root
  cause of *"you ignore all your standing rules"*, so **the fix is to SHRINK and
  HARDEN, not to add rule N+1.**
- **⚠ It got worse today.** The handoff-triggers fix (#119) added 12 lines —
  `config/CLAUDE.md` is now **238 lines**. That change was necessary and correct on
  its own terms, but it is exactly the "add another rule to a saturated file" move
  the audit exists to stop. When the audit runs, the handoff-triggers block is a
  legitimate candidate for extraction to an on-demand file; do not treat it as
  exempt because it is new.
- **Resume:** re-dispatch the harness engineer with the original asks — enumerate
  every rule; classify each as ALREADY-ENFORCED (cite hook `file:line`) /
  MECHANIZABLE (propose a hook, respecting the reliability budget — the operator
  deliberately cut 28 hooks to 9) / NOT-MECHANIZABLE-ESSENTIAL / SITUATIONAL
  (extract to on-demand); report line arithmetic; flag contradictions and dead
  references; and say where the root-cause rule (item 3) belongs and what it displaces.

## 3. "Root Cause Over Symptom" rule — BLOCKED on item 2

- **Artifact:** full drafted rule text at
  `docs/handoff/2026-07-24-write-guard-allowlist-and-claudemd-audit.md:19`. It is
  **written nowhere else** — it has never landed in any instruction file.
- **Origin:** standing operator directive, verbatim — *"I never want to see a fix
  like ff866aa again. we solve problems by dealing with the underlying issue, not by
  masking the symptoms."*
- **Why blocked:** deliberate. Adding line 227+ to a saturated file is itself the
  symptom-masking move the rule prohibits. The block is a decision, not an oversight.
- **Resume:** land it only after item 2 returns and says where it goes and what it
  displaces. Copy the drafted text verbatim — it is already reviewed.

## 4. `commands/` not in `scripts/deploy.sh` — QUEUED

- **Verified this session:** `grep -n "commands" scripts/deploy.sh` returns **nothing**.
  `commands/` holds **22 `.md` files**. `~/.claude/commands/` exists and is populated
  from other sources, so the two are silently divergent.
- **Consequence on record:** `memory/feedback-always-route-through-build.md` notes
  `/build` is by design an alias to `/coding-team`, but **the deployed copy is a stale
  broken fork** precisely because `commands/` never deploys.
- **Resume:** first decide whether `commands/` *should* deploy (it may be intentional
  that these are not symlinked). If yes, wire it into `deploy.sh` following the
  existing symlink pattern, and reconcile the stale `/build` copy. Check for
  collisions with the plugin-provided commands already in `~/.claude/commands/`
  before symlinking anything.

## 5. Self-modifying hook — BLOCKED ON A HUMAN DECISION

- **Artifact:** `docs/tickets/2026-07-25-self-modifying-hook-no-safe-edit-path.md`
  (3.3 KB). Lists four options at `:46-54` and **deliberately picks none.**
- **Hazard:** editing `hooks/write-guard.py` or `hooks/_lib/*` can wedge the session
  doing the editing — the live hook imports them, a crash blocks ALL Edit/Write for
  every agent at once, and `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT` cannot recover it
  (it is read after the crash point). Occurred 3× on 2026-07-25. A plain `import`
  check is NOT sufficient evidence — it has passed while wedged.
- **The four options:** (1) fail **open** specifically for `NameError`/`ImportError`;
  (2) import from a frozen/deployed copy rather than the live symlink; (3) a
  pre-commit/pre-edit syntax-and-smoke gate on `hooks/**`; (4) accept as-is and rely
  on stop-and-report (`rules/hook-bypass.md`).
- **Resume:** this needs the operator to choose. Do not pick for them. Until then the
  working mitigation is the probe protocol: one self-consistent edit, then run the
  dummy-event smoke against the LIVE hook, and stop-and-report rather than repair via
  Bash if it wedges.

## 6. Four known write-guard gaps — DEFERRED, each needs its own plan

Recorded per `rules/finding-integrity.md`; all documented in
`docs/handoff/2026-07-26-write-guard-allowlist-COMPLETE.md` and PR #118's body.
Deliberately not folded into the allowlist work — they widen the blast radius from
"who is authorized" to "what counts as an instruction file", which is a different review.

1. **Ungated symlink alias** — `is_instruction_file()` classifies the lexical payload
   path, so `notes/x.txt` → `agents/X.md` is not gated.
2. **Case-insensitive filesystem** — on APFS `skills/demo/skill.md` reaches the gated
   `SKILL.md` without matching the case-sensitive basename set.
3. **Frontmatter beyond the 4096-char window**, and unterminated frontmatter, both
   make discovery return no plan — silently disarming the gate.
4. **General stale-POSITIVE cache hole** — only its *authorization* consequence was
   closed (D1's uncached re-check). Needs an mtime-preserving status change to
   trigger, so the window is narrow.

---

## Tooling note

**codesight is mispointed for this repo.** It rejects the path as outside its trusted
`/Users/cevin/src/` prefix, and its "coding-team" index returns ZERO results for
classes that demonstrably exist. Agents fall back to Grep/Read correctly, so nothing
was lost — but an index that returns *empty* rather than *erroring* reads as "no
callers found" and gets trusted. Re-point it before any audit leans on it.
