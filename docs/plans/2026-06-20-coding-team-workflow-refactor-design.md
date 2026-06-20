---
title: Coding-Team Workflow Refactor — Architecture Proposal
status: proposal
date: 2026-06-20
revised: 2026-06-20 (red-team pass — Workflow API claims checked against code.claude.com/docs/en/workflows; codebase line-refs re-verified; see §0)
author: EM (harness)
decision: D199 (pending)
scope: design-only — no code in this pass; build gated on EM/user approval
---

# Coding-Team Workflow Refactor — Architecture Proposal

## 0. Verification status (red-team pass, 2026-06-20)

This proposal rests on two bodies of fact: (a) what the Claude Code **Dynamic Workflows** feature actually does, and (b) what the current `coding-team` codebase actually contains. Both were checked. Summary:

**Workflow API — confirmed by docs** (`code.claude.com/docs/en/workflows`): the feature is real (requires Claude Code v2.1.154+), runs subagents in the background, exposes `parallel()`, supports resume via `resumeFromRunId` (completed agents return cached results), enforces a **1000-agent lifetime cap** and **~16 concurrent-agent** limit, surfaces live progress via `/workflows`, and deploys from `~/.claude/workflows/`. Custom `agentType`/`subagent_type` dispatch is supported.

**Workflow API — NOT confirmed (assumptions to validate in the pilot, flagged ⚠️ inline):**

- ⚠️ **`agent()` `schema` option** (structured/typed output driving JS — §3.2) — not in public docs. The judgment-gated-25% pattern depends on this; if it's absent, fall back to parsing a delimited text verdict from the agent.
- ⚠️ **`pipeline()` and `log()` primitives** — only `parallel()` is documented. Treat `pipeline()` as "sequence with `await`" and `log()` as "may be `console.log` / run-output" until confirmed.
- ⚠️ **"100% cache hit on same script + args"** — resume/caching exists; the exact guarantee is unverified. Don't design correctness around perfect caching; design around "completed agents *may* be cached."
- ❗ **CORRECTED premise — "a Workflow cannot pause for user input" is false as stated.** Per the docs, tool calls outside the allowlist *do* prompt mid-run. What's actually true: a Workflow has **no API for posing an arbitrary question and branching on the answer** (the only interactive surface is allow/deny permission prompts on tool calls), and the docs *recommend pre-allowlisting* to avoid unwanted interruptions. The hybrid architecture (§3) survives — it just needs the corrected justification, applied below.

**Codebase claims — verified in place.** File sizes (§1/§8), the six `ct-*` agents (§3.1), `deploy.sh`'s source→symlink model, `session-resume.md`, `task-weight.md`, and the write-guard comments (§6) all check out. Five line-references had drifted and are corrected in this revision: spec gate `SKILL.md:113→115`, BLOCKED `execution.md:138→139`, design respawn `design-team.md:22→23`, audit-budget `audit-loop.md:51→53`, Codex challenge `audit-loop.md:63→65`. Also: the security-escalation skill is `/scan-security` (not `/scan-adversarial`), and `ci-fix-protocol.md` says "retry 2 or 3" rather than a hard max-3 loop — noted in §2.

## 1. Goals (ranked, per EM decision)

1. **Reliability / determinism** — move pipeline control flow (fan-out, fix-loops, gate-running) out of model-followed prose and into a deterministic `Workflow` script. Directly attacks the recurring toxicity failure modes: Case 24 (MANDATORY labels decay past ~200 lines), Case 37 (agents process ~50% of enumerated items then report done), Case 42 (gates skipped under context pressure). A `for` loop runs every iteration because it is code, not because a model remembered.
2. **Shrink instruction files** — `phases/execution.md` (14.3K) + `audit-loop.md` (5.9K) + `post-execution-review.md` (5.4K) + `execution-reminders.md` (4.6K) ≈ 30K of orchestration prose whose job is to make the model emulate a scheduler. A script does the scheduling; the prose shrinks to gate-handling + agent-prompt content only.
3. **Latency / performance** — the orchestrator currently re-reads phase files each turn and dispatches serially. A Workflow runs once, with a real concurrency scheduler (cap ~16), fanning out audits/specialists in parallel without re-reading prose every turn.

These goals are mutually reinforcing: the same move (control-flow → code) buys all three.

## 2. Current-state map (evidence)

Source: full read of `SKILL.md` + all `phases/*.md` (investigation 2026-06-20).

- **~75% of agent dispatch points are fixed-shape** (parallel barriers, fix-loops-until-clean, pipeline sequences) — directly Workflow-convertible.
- **~25% are judgment-gated** (worker selection, thin-output respawn, BLOCKED triage, DONE_WITH_CONCERNS routing, CI-unknown classification) — convertible only by wrapping the judgment in a schema'd `agent()` whose structured verdict drives JS.
- **Every phase is bracketed by interactive user gates** — approve approach (`SKILL.md:101`) → approve design doc (`SKILL.md:108`) → confirm spec (`SKILL.md:115`) → plan 2nd-opinion + "ready to execute?" (`planning-next-steps.md:18`, `execution.md:5`) → 4 completion options (`completion.md:35`). These are arbitrary-question gates with no Workflow-native equivalent (see §0/§3), so they stay in the interactive loop.

Fixed-shape patterns already present (and their Workflow-native equivalents):

| Existing pattern | file:line | Workflow primitive |
|---|---|---|
| Design team: N specialists → cross-review → synthesis | `design-team.md:9-44` | `parallel()` → synthesize |
| Per-task audit: 2–5 auditors simultaneously | `audit-loop.md:11-21` | `parallel()` fixed-arity |
| Audit fix loop (max 3, fresh agents) | `audit-loop.md` | `while(round<3 && findings)` |
| Spec-doc reviewer fix loop (max 3) | `spec-review.md:12` | `pipeline` + per-item verify |
| Plan-doc reviewer fix loop (max 3) | `planning.md:184-193` | `pipeline` + per-item verify |
| Per-task loop: implement → audit → fix | `execution.md` | `pipeline(tasks, …)` |
| Exit sequence: QA → doc-drift → post-exec review | `execution.md:161-183` | `pipeline()` sequential |
| CI fix loop (retry 2–3) | `ci-fix-protocol.md:53-65` | `while(attempts<3 && !green)` |

> Note: `ci-fix-protocol.md` phrases the cap as "retry 2 or 3," not a hard `max 3`. The Workflow should encode an explicit `MAX=3` invariant — this is exactly the kind of soft prose-cap (Case 37) that determinism is meant to harden.

## 3. Core architectural decision: hybrid (gates in the loop, spans in the script)

A `Workflow` runs in the background and **has no API for asking the user an arbitrary question and branching on the answer** — its only interactive surface is allow/deny permission prompts on non-allowlisted tool calls, and the docs recommend pre-allowlisting to suppress even those (§0). It is therefore unsuitable for hosting the approve-this-approach / confirm-this-spec / pick-one-of-four-completion-options gates, which are exactly arbitrary-question decision points. Therefore the only viable architecture is a **hybrid**:

- The **interactive main-loop orchestrator** (the skill, much slimmed) owns every user gate: it asks, waits, and on approval **calls a Workflow** for the deterministic span that follows.
- Each **Workflow script** owns one phase's deterministic fan-out, returns a structured result, and the loop runs the next gate.

```
MAIN LOOP (interactive, slim)                 WORKFLOW SCRIPTS (deterministic, background)
─────────────────────────────                ───────────────────────────────────────────
Phase 1: ask → approve approach ───────────►  (none — pure dialogue)
present design ◄───── approve ───────────────  design_team.workflow.js   parallel(specialists)→synth
confirm spec ──────────────────────────────►  spec_review.workflow.js    reviewer fix-loop
approve plan + 2nd-opinion Y/n ────────────►  planning.workflow.js       planner→reviewer loop
"ready to execute?" ───────────────────────►  execution.workflow.js      pipeline(tasks: impl→audit→fix) + exit gates
present 4 completion options ◄───────────────  (loop executes choice; optional ci_fix.workflow.js)
```

The seam is **each phase's entry/exit gate** — the cleanest possible boundary, because the gates already exist there.

### 3.1 Key enabler: `agent()` reuses the existing ct-* agents

`Workflow`'s `agent()` dispatches a custom `agentType`/`subagent_type` resolved from the same registry as the Agent tool (confirmed, §0). So the scripts dispatch the **exact same** `ct-implementer`, `ct-spec-reviewer`, `ct-simplify-auditor`, `ct-harden-auditor`, `ct-qa-reviewer`, `ct-harness-engineer` agents we already maintain (all six verified present in `agents/`). The agent *definitions* don't change; only the *orchestration that calls them* moves from prose to code. This is what makes the refactor tractable rather than a rewrite.

> ⚠️ **Pilot must confirm the exact `agent()` signature.** The `agentType` dispatch is documented; the precise option name (`agentType` vs `subagent_type`) and the `schema` option below are not. Step 1 of the migration (§11) should begin by generating one trivial workflow and reading back its real API before any pipeline code is written.

### 3.2 Encoding the judgment-gated 25%

Judgment points become **schema'd `agent()` calls whose structured output drives a JS conditional** — the judgment stays with a model, but the *control flow off that judgment* becomes deterministic:

> ⚠️ **Depends on the unverified `schema` option (§0).** If `agent()` has no structured-output `schema`, the same pattern works by having the agent emit a fenced verdict block (e.g. `<<<VERDICT {"thin":true}>>>`) that the script parses — slightly less clean, equally deterministic. The pilot picks whichever the real API supports; the architecture does not change either way.

```js
// Thin-output respawn (design-team.md:23, SKILL.md:79) — was: "Team Leader respawns if thin"
let out = await agent(specPrompt, {agentType: 'ct-implementer', schema: WORK})
const q = await agent(`Is this output thin/off-scope? ${out.summary}`, {schema: {thin:'boolean', why:'string'}})
if (q.thin) out = await agent(tighterPrompt, {agentType: 'ct-implementer', schema: WORK}) // exactly 1 respawn, enforced by code

// BLOCKED triage (execution.md:139) — structured verdict, not prose interpretation
if (impl.status === 'BLOCKED') {
  // workflow returns control to the loop with a typed reason; loop surfaces to user (gate)
  return {halt: 'BLOCKED', reason: impl.blockedReason, task}
}
```

The respawn cap, the audit arity, the fix-round cap (max 3) — today these are prose the model may under-apply (Case 37). As code they are invariants.

## 4. Per-phase convert / keep table

| Phase | Interactive gates → stay in loop | Deterministic span → Workflow | Convert priority |
|---|---|---|---|
| 1 Dialogue | approach approval, rejection, scope-decomp | none | N/A (no fan-out) |
| 2 Design Team | design-doc approval, 2nd-opinion offer | `parallel(specialists)` → cross-review → synth | High (retires stale `Teammate()` API) |
| 3 Spec Review | spec confirm, 2nd-opinion offer | spec-doc reviewer fix-loop (max 3) | Medium |
| 4 Planning | plan 2nd-opinion (required M/L), tiebreaker, context prompt | planner → plan-doc reviewer loop (max 3) | Medium |
| 5 Execution | exec-start, worktree, BLOCKED ×2, audit-budget, security escalation, context prompts | per-task: impl → `parallel(audit 2–5)` → fix-loop; then QA → doc-drift → post-exec | **Highest (pilot here)** |
| 6 Completion | 4-option choice, wiki, decision-log, CI options | CI fix loop (max 3) | Low |

## 5. The one genuinely hard wrinkle: gates *inside* a deterministic span

A few interactive gates sit **inside** otherwise-deterministic spans and so cannot simply be hoisted to the phase boundary:

- Audit-budget 30% check (`audit-loop.md:53`) — asks the user mid-loop.
- Audit loop-cap Codex `challenge` offer (`audit-loop.md:65`).
- Security escalation `/scan-security` recommendation (`execution.md:108`).
- Post-exec `/second-opinion review` gate (required at M/L).

Three resolution patterns (the design picks per-gate, documented in the build plan):

1. **Hoist to boundary** — move the decision before/after the span (works for the post-exec 2nd-opinion: the loop offers it after `execution.workflow.js` returns).
2. **Autonomous default + log** — for budget/escalation thresholds, the workflow auto-applies the documented default (e.g. defer medium/low past 30%, continue) and `log()`s it; the loop surfaces a summary the user can override. Aligns with "user has Esc" (Case 15).
3. **Early-return for decision** — the workflow returns `{needsDecision: …}`; the loop asks; re-invokes with `resumeFromRunId` so already-completed agents return cached results and only the post-decision tail re-runs.

Pattern 3 leans on Workflow's native resume (`resumeFromRunId`; §0). ⚠️ The exact caching guarantee is unverified, so do not make correctness *depend* on a cache hit — pattern 3 must remain correct even if the tail re-runs some completed agents (idempotent, just slower). With that caveat it also doubles as the crash-recovery story (§7).

## 6. Hook / session-state compatibility — VERIFIED COMPATIBLE

The Phase 5 write-guard is **dispatch-agnostic by design** and survives the refactor unchanged:

- `hooks/write-guard.py:102-106` (verbatim): the PreToolUse hook "fires identically inside a dispatched sub-agent — Claude Code's PreToolUse event payload carries no reliable session_id / cwd / transcript_path."
- `:154-157`: pipeline state "is derived from the active plan file … the unique plan whose YAML frontmatter declares `status: in-progress`."

A Workflow's `agent()` subagents call `Edit`/`Write` through the same tool layer → trip the same PreToolUse hook → which reads the same plan-status filesystem state. **No hook change required.** The main loop sets the plan `status: in-progress` before calling `execution.workflow.js` (as it does today at `execution.md:38-42`), arming the guard for every workflow-dispatched agent.

Secondary `/tmp/coding-team-*` session files (`SKILL.md:161`, used for completeness checks + recursion protection) are a smaller concern — the build plan must confirm the workflow run sets/reads them, but the *core* guard does not depend on them.

## 7. Resumability — reconcile two mechanisms

Two resume systems must be unified, not left to collide:

- **Today:** `phases/session-resume.md` — model re-reads plan + `git status` to rebuild context after a `/clear` or compaction.
- **Workflow-native:** `resumeFromRunId` — completed `agent()` calls return cached results; only edited/new calls re-run (confirmed; exact cache-hit rate unverified — §0).

Proposed: the main loop persists each phase's Workflow `runId` (in the plan frontmatter or a sidecar) so a resumed session re-invokes with `resumeFromRunId` and skips re-running finished agents *where the cache allows*. `session-resume.md` shrinks to "find the active plan + its last runId, re-enter at that gate." Net: resume gets *more* reliable (the plan-status filesystem state in §6 remains the source of truth even if a cache miss forces a re-run) and the prose shrinks.

## 8. Expected instruction-file shrinkage (the toxicity win)

Rough, to be confirmed in the build:

| File | Today | After (gate-handling + prompts only) |
|---|---|---|
| `execution.md` | 14.3K | ~5–6K |
| `audit-loop.md` | 5.9K | folded into `execution.workflow.js` |
| `execution-reminders.md` | 4.6K | mostly folded into script |
| `post-execution-review.md` | 5.4K | ~2K (gate text) |
| `design-team.md` | 8.8K | ~4K (retires `Teammate()` choreography) |

The orchestration logic moves into `*.workflow.js` (code, not counted against the 200-line MANDATORY-decay ceiling). Agent prompt bodies stay in `agents/ct-*.md` (already under the cap post-D194). Net: the highest-toxicity files drop below the danger line for the reason that *the model no longer has to emulate a scheduler from prose*.

## 9. Risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Workflow has no arbitrary-question API mid-script (corrected from "can't pause" — §0) | High | §5 three-pattern resolution; pilot proves it on the post-exec 2nd-opinion gate |
| Unverified API surface (`schema`, `pipeline()`, `log()`, cache rate) | High | §0 lists each; §11 step 1 reads the real API from a throwaway workflow before writing pipeline code; every dependent pattern has a documented fallback (§3.2, §5) |
| Judgment lost when prose → code | Med | §3.2 schema'd-agent pattern keeps judgment with a model; only control-flow becomes code |
| Runaway agent spawn / cost | Med | Workflow's 1000-agent lifetime cap + explicit per-loop caps (max-3 already exists); `log()` every truncation (no silent caps) |
| Two resume systems diverge | Med | §7 unify on `resumeFromRunId` keyed in plan frontmatter |
| `/tmp` session-file assumptions | Low | §6 — core guard is plan-status-based; confirm secondary files in build |
| Workflow is newer/less battle-tested than the prose pipeline | Med | **Pilot one phase**, run it in parallel with the prose path on real tasks before converting the rest; keep prose as fallback until the pilot is proven |
| Debuggability (a failing script vs. a failing prose step) | Med | `/workflows` live progress + `log()` narration; design mandates a `log()` at each gate-equivalent |

## 10. Recommendation: pilot Phase 5 first

Convert **only `execution.workflow.js`** (the per-task implement→audit→fix loop + the exit-gate sequence) as the proof-of-concept, because it is simultaneously:
- the **highest-value** (most gates, most fan-out, biggest prose, most skip-risk), and
- the **hardest case** (parallel audit barrier + fix-loop + judgment respawns + the gate-inside-span wrinkle).

If the pattern holds for Phase 5, Phases 2/3/4/6 are strictly easier. If it doesn't, we learned it cheaply on one phase with the prose pipeline still intact as fallback.

## 11. Proposed migration sequence (post-approval)

1. **API spike (do this first)** — author a throwaway 20-line workflow that dispatches one `ct-implementer` and resumes once. Confirm the real `agent()` signature, whether `schema`/`pipeline()`/`log()` exist, and observe resume/caching behavior. Resolve every ⚠️ in §0 before writing pipeline code. Cheap, hours not days.
2. **Pilot** — author `execution.workflow.js`; main loop calls it behind a flag; run both paths on a real Medium task; compare audit coverage + correctness.
3. **Harden** — resolve the §5 gates, the §7 resume keying, confirm §6 secondary session files.
4. **Convert** — Phases 2, 3, 4 (all simpler fix-loops/fan-out).
5. **Convert** — Phase 6 CI loop.
6. **Shrink** — delete the superseded prose from `phases/*.md`; `session-resume.md` rewrite; `deploy.sh` ships the workflow scripts.
7. **Retire fallback** — remove the flag once parity is proven across tiers.

Each step routes through `/coding-team` (these are behavioral-instruction + code files) with a logged harness prediction per step.

## 12. Open questions for the build phase

- Where do workflow scripts live and deploy from? (`skills/coding-team/workflows/*.js` source → `~/.claude/workflows/` via `deploy.sh`, matching the source→deploy model — F-2 in memory.)
- Does the tier classifier (`task-weight.md`) move into the workflow as a pure function, or stay in the loop and pass `tier` as `args`? (Leaning: compute in loop, pass as `args`; the workflow gates `agent()` calls on it.)
- Trivial/Small fast-lane: does it skip the workflow entirely (single agent in the loop) or call a degenerate workflow? (Leaning: skip — the fast lane has no fan-out to schedule.)
- How does `/second-opinion` (itself a skill) compose with a workflow `agent()` — sub-workflow, or stay a loop-level gate? (Leaning: loop-level gate; it's interactive.)

---

**Next action:** EM/user approves this proposal → log D199 prediction → route the Phase 5 pilot through `/coding-team` as a design+build task. No code until then.
