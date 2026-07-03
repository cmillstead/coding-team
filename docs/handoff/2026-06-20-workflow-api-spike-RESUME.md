# RESUME — Workflow API spike (D199 §11 step 1)

> **STATUS UNCONFIRMED as of 2026-07-02 audit: D199 still pending; verify whether this spike ran before acting.**

**Trigger:** user `/clear`'d, then "do the api spike." This is the first build step of the coding-team Workflow refactor.

## What this is
The architecture proposal (`skills/coding-team/docs/plans/2026-06-20-coding-team-workflow-refactor-design.md`) recommends a hybrid: interactive loop owns user gates, `Workflow` scripts own deterministic fan-out spans. Before ANY pilot code, §11 step 1 demands a throwaway API spike to resolve the §0 ⚠️ unknowns.

## The spike — confirm these against the REAL Workflow API (not docs/memory)
Run a minimal inline `Workflow` (the tool accepts an inline `script`). Author a ~20-line script that:
1. Dispatches ONE trivial agent via `agent(prompt, {agentType/subagent_type: 'ct-implementer' OR a trivial type})` — **confirm the exact option name**: `agentType` vs `subagent_type`.
2. Tests whether **`schema`** (structured/typed output) exists on `agent()` — the judgment-gated-25% pattern (§3.2) depends on it. If absent, fallback = parse a fenced `<<<VERDICT {...}>>>` block from agent text.
3. Tests whether **`pipeline()`** and **`log()`** primitives exist (only `parallel()` is doc-confirmed). If absent: `pipeline()` → sequence-with-await; `log()` → console.log/run-output.
4. Observe **resume/caching**: re-invoke with `resumeFromRunId` and see if the completed agent returns cached (claim is "100% on same script+args" — UNVERIFIED).

Keep it cheap (one agent, trivial prompt). The goal is API facts, not real work. `/workflows` shows live progress.

## State at handoff (all clean)
- D195–D198 + D199 proposal: ALL merged to `main`, both repos synced. Parent records submodule `b1885b0`; pointer in sync, zero drift.
- Predictions D196, D197, D198 pending `/harness-engineer verify`. **D199 prediction NOT yet logged** — log it when the pilot build actually starts (the spike is pre-pilot recon; per the doc, "EM approves → log D199 → route Phase 5 pilot").
- Pre-existing `TestMigrationGuard` ×2 failures in submodule — unrelated, untouched.

## After the spike
Update §0/§3.2/§5 of the design doc with the confirmed API facts (resolve every ⚠️), then the doc is build-ready and the Phase 5 pilot can be routed through `/coding-team`.

## Gotchas this session
- `skills/coding-team/docs/plans/` is **gitignored** (ephemeral) — durable docs there need `git add -f`.
- Agent teams ARE available (Agent with `name`+`run_in_background`; team tools deferred — ToolSearch them). Don't false-negative this.
- `~/.claude/skills/coding-team` is a submodule; commit there, then bump parent pointer.
