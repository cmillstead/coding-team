# Handoff — Group A reference-extraction execution in flight (2026-07-26)

Written before dispatching T4, the plan's largest and riskiest task.

## State

- **Branch:** `feat/reference-extraction-group-a` (branched from `main` @ `2a2da47`)
- **Plan:** `docs/plans/2026-07-26-reference-extraction-group-a.md` — **`status: in-progress`**,
  gitignored, 1201 lines. It is the ONLY armed plan; `write-guard.py` is live against
  its 14 declared `instruction_files:` paths.
- **Baseline:** `python3 -m pytest hooks/tests -q` → `1054 passed, 9 skipped`; `ruff check .` clean.

## Landed and independently verified (not just agent-reported)

| Task | SHA | What |
|---|---|---|
| T1 | `ea17b7f` | `reference/` deploy loop + missing `rules/` prune loop in `scripts/deploy.sh`; 2 tests |
| T2 | `9f1405d` | named `mcp-resilience.md` in 5 auditor codesight-fallback lines; line counts unchanged |
| T2b | `d02f44f` | hoisted 3 rules into `memory/consolidated-feedback.md` (items 8, 11 tightened in place; new 18) |
| T3 | `e75c0c1` | `test_agent_rule_refs.py` extended to guard `reference/`; union assertion at `:122-123` |

## Remaining: T4 → T5 → T6 → T7. Do not reorder.

- **T4** (plan `:667`) — the atomic move: 5 files `rules/` → `reference/`, every consuming
  path rewritten, `deploy.sh` run for real. Single commit by design: it is the only commit
  where a rule could become unreachable, and criterion 9 depends on it staying atomic.
- **T5** (`:892`) — correct the false "not an auto-load rule" comments at the destination.
- **T6** (`:953`) — `rules/README.md` warning that `rules/` is unconditionally always-loaded.
- **T7** (`:1050`) — end-to-end verification.

**Target:** `wc -l ~/.claude/rules/*.md` drops 226 → 116.

## Standing constraints

- Never `git add -A`. Never stage `.claude/settings.local.json`, `docs/plans/`, or the
  untracked `skills/second-opinion/codex-learnings.d/2026-07-23-*.md`.
- Never set `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT`. If the guard blocks, STOP and report.
- **Dispatch implementers WITHOUT `name`** — passing `name` silently forces background and
  costs the inline report (measured this session; see `feedback-agent-idle-without-report`).
- Verify every agent claim by command. Two agent diagnoses were wrong this session while
  their conclusions were right.

## Known pre-existing failure — NOT ours, do not fix

`skills/second-opinion/scripts/test_build_digest.py::test_design_face_output_is_byte_identical_to_committed_digest`
fails because the untracked entry file `codex-learnings.d/20260723-170559-5689-self-heal-migration-schema-shape.md`
is rendered into the generated digest but absent from the committed one. Root-caused by
command this session. Out of `pytest hooks/tests` scope, which is why the baseline is green.
Resolution is the operator's: commit the entry and regenerate, or delete the file.

## Open, needing the operator

1. **PR #95** — audit recommends close + re-land only its second rule (~4 lines instead of 22).
2. **Self-modifying hook ticket** — `docs/tickets/2026-07-25-...md`, four options, none picked.
3. **Remaining saturation phases** — Groups B/C/D, F1/F2/F3, and the Root Cause rule
   (unblocked; audit says it lands after `# Your Role`, displacing the Engram CLI block).
4. **`rules/*.md` is not gated by write-guard** — 12 always-loaded files any agent may edit
   with no plan declaration, while conditionally-loaded `agents/*.md` are gated. Found this
   session, belongs in the enforcement phase.
