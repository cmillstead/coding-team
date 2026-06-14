# coding-team Process-Weight Asymmetry Audit — 2026-06-14

**Trigger:** "Development seems slow these days." Diagnosis confirms coding-team still dispatches subagents correctly — the slowness is **process weight**, not a broken dispatch.

**Root cause (one sentence):** Every gate in the pipeline was hardened against *under-compliance* (NEVER skip, named rationalizations that seal every escape valve) but never against *over-compliance* — there is no strongly-framed fast lane, so a one-line fix pays the same maximum ceremony as a 20-file feature.

Two compounding sources: (A) instruction-file weight asymmetry, (B) hook hot-path latency.

---

## A. Instruction-File Weight Asymmetry (34 findings)

### The pattern
Strong framing on the heavy path (`MUST`, `NEVER skip`, "required not offered", iterate-until-PASS, named rationalizations naming "it's small" as a violation) + weak-or-absent framing on the right-sizing escape (`may`, `can`, buried in another file, or actively punished). The existing QA-reviewer skip (`1 task AND ≤3 files`) proves the authors know how to write a quantified fast lane — it just wasn't applied to the other gates.

### P1 — forces heavy path on trivial tasks, no escape

| # | File:Line | Gate | Why P1 |
|---|---|---|---|
| 1 | planning.md:195-202 | Codex `/second-opinion review` on plan, iterate-until-PASS | Unconditional external round-trip; only escape is `which codex` failing |
| 2 | SKILL.md:124 | Phase 4 exit Codex gate | Same gate reinforced at SKILL level, no weight condition |
| 3 | SKILL.md:132-133 | Phase 5 exit gate 4 (post-exec Codex) | QA-reviewer skip (gate 2) does NOT propagate to the Codex gate (gate 4) |
| 4 | post-execution-review.md:17,20-21 | "Always run review"; rationalization seals the risk-signal escape | Risk signals gate only `challenge`, never `review` — ritual with no effect |
| 5 | planning.md:188 | Codex tiebreaker on 2nd reviewer pass | A small plan hitting 2 review rounds = 4 serial external calls |
| 6 | completion.md:1-2,13 | Full test suite re-run at Phase 6 entry | Re-runs suite that passed seconds earlier in Phase 5; rationale always-true so escape unreachable |
| 7 | completion.md:59-67 | Full suite re-run pre-push (3rd run) | Three sequential full-suite runs per PR |
| 8 | completion.md:96 | "Do NOT skip saving" completion summary | Retro file written for every run incl. one-line typo fix |
| 9 | dialogue.md:1-14 | Full question→approach→approval cycle | No bypass for fully-specified tasks |
| 10 | dialogue.md:12 | "Do NOT create Team Leader until approved" | No exception when approach already given in the request |
| 11 | design-team.md:1-9,26-39 | Full design-team lifecycle | No path to skip Phase 2 entirely; 2-worker team still runs full lifecycle |
| 12 | design-team.md:126 | "Design work almost always routes to agent teams" | "almost always" = dead exception, no criteria; reads as "always" |
| 13 | named-rationalizations.md:17-18 | "trivial instruction file change" punished | Self-enforcing: names right-sizing as the compliance trigger; even whitespace/comment edits forced through Agent tool |
| 14 | execution-reminders.md:9 | "second-opinion gate mandatory regardless of plan size" | User override exists only in a different file, not cross-referenced here |
| 15 | planning-next-steps.md:53-59 | 3 rationalization suppressors target right-sizing; user override weaker than the suppressors | Escape framed weaker than the things suppressing it |

### P2 — escape exists but too weak to fire

| # | File:Line | Gate | Escape weakness |
|---|---|---|---|
| 16 | execution.md:113-116 | Verification subagent per task | Escape gated on context>80%, not task weight |
| 17 | audit-loop.md:65 | Codex framing inconsistency | Same tool "required" in 3 places, "offered" in 1, no governing principle |
| 18 | completion.md:113-149 | Wiki article generation | User must opt OUT via menu; should auto-skip when summary is empty |
| 19 | spec-review.md:2-3,9 | spec-doc-reviewer dispatch | No scope gate; single-method spec gets same heavyweight reviewer |
| 20 | doc-drift-scan.md:1-9 | Doc-drift scan | 3rd skip condition requires advance plan authoring; no judgment-based fast lane |
| 21 | dialogue.md:4-8 | "2-3 approaches" | Forces inventing a 2nd approach when only one is sensible |
| 22 | design-team-context-retrieval.md:51-58 | golden-principles read + pass-through | No skip when task has no architectural decisions |
| 23 | memory-nudge.md:1-113 | 3-pass memory extraction | User can decline persistence, but all analysis runs unconditionally |
| 24 | plan-format.md:43 | Context Brief "MUST fill" | Boilerplate fallback = always written even for trivial plans |
| 25 | plan-format.md:48,63 | Eval criteria "MUST check" | Skip condition sequenced after the MUST |

P3 (minor, lower priority): design-team.md:79-86 (team-sizing floor of 2), dialogue.md:3 (re-reads context), session-resume.md:3-18 (orphan PR check), named-rationalizations.md:38-41 (no escape for genuinely pre-existing failures), completion.md:190-227 (decision-log prompt always asked).

### Positive template to copy
`session-resume.md:88-112` — context refresh gated on `HOURS_SINCE > 24` with the skip path stated at equal force. This is exactly how every other gate should be written.

---

## B. Hook Hot-Path Latency (ranked)

| Rank | Hook | Event | Cost | Fix |
|---|---|---|---|---|
| 1 | builder-self-check.py | PostToolUse Edit\|Write | **Up to 55s** (ruff+mypy+tsc+pytest sequential) on EVERY edit | Move off hot path → `Popen` fire-and-forget to log, surface at Stop; or restrict to test files |
| 2 | git-safety-guard.py | PreToolUse Bash | File I/O + up to 3 git subprocesses on commit paths, every Bash | Cache `has_project_infrastructure()` in state; gate commit-only git calls behind commit detection |
| 3 | loop-detection.py | PostToolUse Bash | Unconditional state file read+write every Bash | Only `save_state()` when failure list actually changed |
| 4 | hook-health-check.py | SessionStart | `gh pr list` 10s blocking + N interpreter spawns | Make `get_pr_throughput()` non-blocking, cache 1h TTL |
| 5 | write-guard.py | PreToolUse Edit\|Write | `find_active_plan()` filesystem scan every edit | Cache active-plan path for session |
| 6 | qmd-vault-embed.sh | PostToolUse Edit\|Write | `jq` subprocess spawn every edit (even non-vault) | Shell-native stdin parse; skip jq for non-vault paths |

Correctly implemented (no change): codesight-hooks.py (non-blocking Popen), deploy-drift-check.py (session-once marker), lint-warning-enforcer.py (fast regex exit), coding-team-lifecycle.py (rare Skill event).

Registration drift noted: git-safety-guard.py has a dead PostToolUse handler not registered in settings.json — harmless but worth cleaning.

---

## Proposed unifying fix: one shared task-weight ladder

All 34 instruction findings collapse to a single missing primitive — a **quantified task-weight classifier** referenced by every gate, replacing per-gate ad-hoc thresholds. Proposed ladder:

| Tier | Definition | Pipeline |
|---|---|---|
| **Trivial** | 1 file, ≤20 lines, fully specified, no arch decision | Skip Phases 1-3; single haiku task in Phase 5; skip Codex gates, QA reviewer, verification subagent, wiki, decision-log. One test+lint run. |
| **Small** | ≤3 files, no new deps/schema/security surface | Skip design team (inline design note); skip plan Codex gate; one post-exec test run; skip wiki unless patterns found. |
| **Medium** | 4-10 files OR any security/schema/dep surface | Full pipeline; Codex `review` required; QA reviewer; one verification pass. |
| **Large** | 10+ files OR architectural change | Full pipeline + Codex `review`+`challenge`; full audit loop. |

Rule: each gate becomes `if tier >= X: run`. Fast lanes get the SAME framing force as the gates (strong, quantified), curing the asymmetry. Codex `challenge` is always *offered*, never *required* — that's the one consistent principle to state once.

---

## Routing note
All fixes are CC instruction-file + hook edits → must route through `/coding-team` (Phase 2 prompt-craft advisory for instruction files; implementer for hooks). EM sets the ladder thresholds; team executes the edits.
