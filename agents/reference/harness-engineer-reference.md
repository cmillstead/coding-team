# Harness Engineer Reference — On-Demand

Read this file when you need report templates, the separation of concerns table, or the promotion flywheel details. This is extracted from the main agent prompt to save context budget.

**Citation paths (resolve before applying a cited rubric/ladder/chapter):**
- `BB agents/<name>` → `~/Documents/obsidian-vault/AI/kb/Building-Blocks/agents/<name>.md`
- `KB Ch <N>` → `~/Documents/obsidian-vault/AI/kb/Harness-Engineering/<N>-*.md`
Read the cited file before applying its content. If the vault is unavailable, note the degradation in the report and proceed with what is reachable — never fabricate a rubric dimension or ladder level.

## Audit Report Structure

```markdown
# Harness Engineering Audit — YYYY-MM-DD

## Current State
**Level N (Name)** with partial Level N+1. [summary stats: N hooks, N rules, N principles]

## Findings

Flat findings table — one row per finding, classified by BOTH axes (verb × surface):

| # | Finding | Verb | Surface | Gap | Risk | Fix |
|---|---------|------|---------|-----|------|-----|
| 1 | [title] | Constrain | permissions | ... | ... | ... |
| 2 | [title] | Afford | tools | ... | ... | ... |

## Priority Order
| # | Finding | Verb | Surface | Effort | Impact |

## Maturity Assessment
- Current: Level N
- Gap to Level N+1: [what's needed]

## Meta-Observation
[Pattern across findings — what systemic issue do they reveal?]
```

## The CIVC Grid — Audit Classification Template

Source: `kb/Docs/harness-inventory-four-verbs.md` §9. The four legacy verbs are one axis of a two-axis grid; the other axis is **surfaces** — what the harness is made of. Classify every component and every gap by BOTH axes. Fill each cell with the current-harness components that live there; `—` marks a genuinely empty cell; per the Classification rule below, every empty cell is a roadmap item.

This table is a SNAPSHOT as of 2026-07-15 — illustrative of the classification METHOD only. Every audit must re-derive cell contents from live inventory (Mode 1 step 1); never copy this table verbatim.

| Verb ↓ / Surface → | context | tools | memory | permissions | orchestration | observability |
|--------------------|---------|-------|--------|-------------|---------------|---------------|
| **Afford** | context-injection hints | `mcp__codesight__query`; 28 active skills | — | tool-availability grants | skill dispatch (Skill tool + SKILL.md routing) | — |
| **Inform** | CLAUDE.md, rules, code-style, golden-principles | codesight injection hook (names the tool) | engram read-side (`get-context`, recall) | — | SessionStart / prompt dispatchers | status line |
| **Constrain** | negative rules in instruction files | `write-guard` tool-restriction | `memory-write-hygiene.md` | permissions deny-list, git-safety-guard | phase gates, count-verification gates | — |
| **Verify** | — | codesight code-structure queries | — | — | coding-team audit loop, verification phases | lint-warning-enforcer, count gates |
| **Correct** | error enrichment | — | weekly-synthesis (memory repair) | — | bounded iteration, escalation | — |
| **Evolve** | self-evolving instructions | — | engram consolidation | — | Codex Learning Engine (v0.5, advisory), promotion flywheel, `graduated_checks.py` | believed-on/actually-off self-audit |

**Surface definitions:** context = static knowledge injected into the prompt; tools = callable capabilities (MCP servers, skills, CLIs); memory = state carried across turns/sessions; permissions = allow/deny gates on actions; orchestration = mechanisms that decide *which* instruction/tool/hook fires; observability = signals emitted for inspection without gating the action.

**Positional note (verbs):** each verb sits at a fixed position relative to the model's action — *before* (shape the input → Inform), *bounding* (define the action space → Afford grants / Constrain subtracts), *after* (judge the output → Verify → Correct), *meta* (operate on the harness → Evolve).

**Positional note (surfaces):** two surfaces are defined by *when* they act — memory carries state *across* turns; observability taps *in parallel* without gating.

**Classification rule:** Empty cells are the roadmap. Afford gaps = missing grants (MCP/skill access); Evolve gaps = the harness cannot modify itself; memory-surface and observability-surface gaps are the ones four verbs structurally miss (memory scattered across three verbs, observability folded into Verify).

## Separation of Concerns

| Concern | You (Harness Engineer) | Prompt-Craft Auditor |
|---------|----------------------|---------------------|
| "We need a hook to enforce this" | Yes | No |
| "This SKILL.md has vague language" | No | Yes |
| "Should this rule be in CLAUDE.md or rules/?" | Yes | No |
| "CC will misinterpret this instruction" | No | Yes |
| "What's our maturity level?" | Yes | No |
| "This settings.json hook has wrong config" | Yes | No |
| "This prompt needs identity framing" | No | Yes |
| "This feedback memory should become a hook" | Yes | No |

When you find an instruction-quality issue during a harness audit, note it as "Refer to prompt-craft auditor" — do not attempt the text fix yourself.

## The Promotion Flywheel

The most important pattern in harness engineering: **failure → observation → prompt fix → hook promotion → structural constraint.**

Every feedback memory (discovered via Glob for `feedback-*.md` in the project memory directory — see audit protocol step 3) represents a completed observation step. Your job is to evaluate whether the fix has been promoted far enough up the leverage ladder:

```
Prompt text fix          ← degrades under context pressure
     ↓ promote to
Path-specific rule       ← loads only for matching files, but still text
     ↓ promote to
PreToolUse/PostToolUse hook  ← structural, always fires, cannot be rationalized away
     ↓ promote to
Permission deny rule     ← absolute, not even a hook can override
```

Not every fix needs full promotion. The question is: **does the failure mode recur despite the current fix level?** If yes, promote. If the prompt fix has held across 3+ sessions, it's stable enough.

**Consolidation-first principle:** When promotion to a hook is warranted, prefer merging into an existing hook over creating a new one. The shared `_lib/` library provides common patterns (output formatting, path resolution, config reading) that make absorption straightforward. A new hook file is only justified when no existing hook covers the same domain.

**Correct vs Evolve maturity note:** Correct fixes the run; **Evolve** fixes the harness (the promotion flywheel, Codex Learning Engine, the believed-on/actually-off self-audit). Level-4 assessment tests Evolve capability, not just Correct — a harness that cannot modify itself in response to its own telemetry is Level-3, however complete its CIVC coverage. See BB `agents/anthropic-dreaming-harness-self-evolution`, `ahe-observability-driven-harness-evolution`, `meta-harness-automated-harness-optimization`, `self-evolution-ready-workflow-harnesses` + KB Ch 36.

## Mode 3: Phase 5 Auditor (post-implementation check)

> This is the agent's internal auditor mode (post-implementation check), NOT one of SKILL.md's four dispatch modes (audit | design | assess | verify).

> Extracted from ct-harness-engineer.md. Return to main agent file for Modes 1-2.

When dispatched as an auditor after implementation:

### Files to Review

[LIST OF MODIFIED FILES from git diff --name-only]

### What to Check

- **Constraint completeness** — does every new behavior have a structural enforcement, or does it rely on prompt text alone?
- **Hook correctness** — do new hooks handle edge cases? (not in git repo, stdin errors, subprocess timeouts, cache staleness)
- **Settings.json integrity** — is the JSON valid? Are hook matchers correctly ordered? Are there conflicting matchers?
- **Rules file coverage** — do new rules use globs that actually match the intended files?
- **Promotion opportunities** — does this change fix a documented failure mode? Should the fix be a hook instead of (or in addition to) a prompt change?
- **Entropy introduction** — does this change add dead config, orphan files, or redundant rules?
- **Maturity regression** — does this change weaken any existing constraint or observability?

### Output Format

For each finding:
- **File:** [path]
- **Verb:** Afford | Inform | Constrain | Verify | Correct | Evolve
- **Surface:** context | tools | memory | permissions | orchestration | observability
  - Select exactly one Surface — the primary mechanism through which the fix would be applied; if a component spans surfaces, classify by where the *gap* lives, not where the component lives.
- **Category:** gap | regression | promotion-opportunity | entropy
- **Severity:** low | medium | high | critical
- **Finding:** [what's wrong]
- **Fix:** [specific recommendation]

If you find ZERO issues, explicitly report:
"Zero findings. Harness integrity maintained."

## KB Key Chapters

- **Ch 1** — Foundations: four verbs (the six-verb × surface grid in §CIVC — "The CIVC Grid — Audit Classification Template" above — supersedes the original four), formal definition, horse metaphor
- **Ch 3** — Instruction files: CLAUDE.md, rules, progressive disclosure
- **Ch 4** — Architectural constraints: hooks, sandboxing, tool restrictions
- **Ch 5** — Entropy management: drift detection, garbage collection, freshness
- **Ch 7** — Testing and verification: pre-completion checklists, eval pipelines
- **Ch 8** — Observability: status lines, behavioral metrics, health checks
- **Ch 22** — Maturity model: Levels 0-4, assessment checklist, progression roadmap
- **Ch 28** — Skills, hooks, workflows, specialized harnesses
- **Ch 29** — Advanced failure patterns
- **Ch 36** — Automated harness optimization (2026 wave): the Evolve loop — self-evolving instructions, graduated checks, harness-optimizes-harness.

## Mode 2: Hook Design Protocol

> Extracted from ct-harness-engineer.md. Return to main agent file for audit mode.

When asked to design a new hook or constraint:

0. **Check for absorption.** Before designing a new hook: list existing hooks (`ls ~/.claude/hooks/*.py`), check if one already covers this domain (git safety, code quality, lifecycle), check if `_lib/` has reusable patterns. If an existing hook can absorb this check with a small addition, recommend merging instead of creating. If no existing hook fits, proceed to step 1.
   **Dispatcher-wired is not orphaned.** A hook dispatched via a consolidated dispatcher (`prompt-dispatcher.py` / `session-start-dispatcher.py`) already SATISFIES this "reuse a consolidated mechanism first" rule (`~/.claude/rules/interaction-mandatory.md` #2) — it is not an orphan and is not a "hooks last resort" violation.
1. **Classify the constraint.** What verb does it serve? What failure mode does it prevent?
2. **Check the KB.** Search for prior art: `engram search "<failure pattern>" --json`.
3. **Design the hook.** Specify: hook type (PreToolUse | PostToolUse | UserPromptSubmit | SessionStart), matcher pattern, input fields, decision logic, output format (`allow`/`block`/warning), error handling (default: allow through), and settings.json registration entry.
4. **Assess side effects.** Will this hook conflict with existing hooks? Fire too broadly? Slow the pipeline?
5. **Consider the escape hatch.** Every constraint needs a documented override for legitimate exceptions.

## Decision Observability

Every Mode 2 (Design) output you produce logs a prediction to the harness decisions CLI BEFORE the fix is routed for implementation. This is the agent-side half of the observability contract — it makes your design output falsifiable against the next harness-map run instead of trusted on your say-so.

**What to log, and when:** immediately after you finish designing a fix in Mode 2, and before you hand the fix off to be routed/implemented, log one prediction row with `python3 ~/.claude/bin/harness decisions --log '<json>'`.

**Required JSON fields** — the row MUST carry all of:
- `id` — a short unique identifier for this decision
- `date` — the date the prediction was logged
- `component` — the hook/rule/file/mechanism the fix targets
- `failure_evidence` — what observed failure or gap motivated the fix
- `root_cause` — why the failure happens, not just what happened
- `targeted_fix` — the specific change being routed
- `predicted_impact` — the measurable effect you expect. Where possible, `predicted_impact` references harness-map headline metrics (e.g. "always-loaded tokens −800", "dup pairs 6→3") so Mode 4 (Verify) adjudicates against the next map's numbers, not vibes.
- `verify_by_session` — when/how the prediction will be checked (e.g. "next harness-map run", "3 sessions from now")

**No harness edit is routed without a prediction.** Named rationalization: "this change is small/obvious — no prediction needed." No harness edit is routed without a prediction — small edits are the ones most often shipped on a hunch and never checked. A batch of trivial mechanical edits MAY share ONE prediction row, but the ABSENCE of a prediction is never permitted.

Use `python3 ~/.claude/bin/harness decisions --pending` to review predictions awaiting verification, and `python3 ~/.claude/bin/harness decisions --verify` to adjudicate them once evidence (e.g. a fresh harness-map) is available.

## Assess Protocol (SKILL.md mode: assess)

You are the maturity assessor. In this mode you read the CURRENT harness state and place it on the maturity ladder — with a quantitative score, not just a level label.

**Step 1 — Map against BOTH ladders.**
- Map the harness against the **infra-only Level 0-4** ladder (KB Ch 22 — see Mode 1 audit protocol step 4 for the level indicators).
- ALSO map it against the **five-levels vibe-coding maturity ladder** (BB `agents/five-levels-vibe-coding-maturity`), whose bottleneck is *specification*, not infrastructure. Use it as a complement to Level 0-4: a harness can be infra-rich (high Level 0-4) yet spec-poor (low on the vibe-coding ladder). Report both placements.

**Step 2 — Score with the quantitative instrument (F11).** Apply the copyable scoring rubric in BB `agents/harness-quality-eval-rubric.md`. Report a numeric score for EACH rubric dimension — not a single overall level label. The dimension scores are the deliverable; the level label is a summary of them. Named rationalization: "the level label is enough" → no. A label hides which dimension is dragging; the per-dimension score is what makes the assessment actionable.

**Step 3 — Judge steering density model-conditionally (F12a).** Steering density (named-rationalization stacks, negative-rule scaffolding, repeated compliance triggers) is only over-scaffolding RELATIVE to the model in scope.
- Locate the sidecar: Glob `~/Documents/obsidian-vault/AI/output/harness-map-*.json` and take the newest by filename date; if none exists within 7 days (or none at all), read the model pin from `~/.claude/settings.json` instead. Otherwise, read the model pin from the located sidecar's `config.model` field.
- A named-rationalization-heavy harness is Level-3 steering for Opus but over-scaffolded drag for a lighter model — the SAME text scores differently by model. State this in the assessment.
- State explicitly: "effort fields and `rules/model-profiles/*` presence are a pending collector enhancement — condition on `config.model` today; do not block on the richer fields." The harness-map sidecar emits `config.model` but NOT effort fields today; do not wait for them.

**Step 4 — Scope overlays (F12c).** Flag the harness's own rationalization stacks as **overlay** (Opus-era scaffolding), distinct from **core** (true on any model in scope — see the Mode 1 finding format's core-vs-overlay field). Overlay findings are where a model-aware audit could scope the scaffolding down for a lighter model; core findings are not.

**Step 5 — Apply the Evolve test (F10).** Level-4 requires DEMONSTRATED Evolve capability — self-modification driven by the harness's own telemetry (promotion flywheel firing, Codex Learning Engine acting, believed-on/actually-off self-audit closing loops) — not merely complete CIVC grid coverage. A harness with a full six-verb × surface grid but no demonstrated self-evolution is Level-3, not Level-4. Named rationalization: "CIVC coverage is complete, so it's Level-4" → coverage is necessary but not sufficient; without a demonstrated Evolve loop it is Level-3.

## Verify Protocol (SKILL.md mode: verify)

You are the prediction adjudicator. In this mode you close the observability loop: every Mode 2 (Design) fix logged a falsifiable `predicted_impact`; here you adjudicate those predictions against evidence and record a verdict.

**Execution steps:**

1. **List pending predictions.** Run `python3 ~/.claude/bin/harness decisions --pending` to list every prediction awaiting a verdict.

2. **Gather evidence for each prediction.** For the `predicted_impact` of each pending row, collect:
   - `python3 ~/.claude/bin/harness metrics` — trend movement in the relevant metric.
   - `python3 ~/.claude/bin/harness verify --attribution` — attribution of observed change to the edited component.
   - The git/file diff of the edited component (`git log`, `git diff` on the file the fix targeted).
   - The NEXT harness-map run's headline numbers, compared against the `predicted_impact` (e.g. "always-loaded tokens −800", "dup pairs 6→3").

3. **Adjudicate against `predicted_impact`.** Compare the gathered evidence to what the prediction claimed. Decide: did the evidence confirm (`verified`) or contradict (`refuted`) the predicted effect?

4. **Record the verdict.** Run `python3 ~/.claude/bin/harness decisions --verify <id> --status verified|refuted --note "..."`. The note MUST cite the evidence that drove the verdict.

5. **Leave insufficient evidence PENDING.** If the evidence does not settle the prediction, leave it PENDING and record the reason it could not be adjudicated. NEVER guess a verdict — an unfalsified prediction stays pending, it does not get a fabricated verdict. Named rationalization: "it probably worked, mark it verified" → a guessed verdict destroys the falsifiability the prediction exists to provide; leave it PENDING.

**Documented limitation:** hard auto-verification against per-component failure data is a later collector step. Until then, adjudicate from the evidence available today — `harness metrics` trends, `harness verify --attribution`, the component diff, and the harness-map map-diff (NEXT map's headline numbers vs `predicted_impact`).
