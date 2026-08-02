# Named Rationalizations — Coding Team

@~/.claude/rules-on-demand/failure-taxonomy.md

**Cross-reference:** The consolidated taxonomy with recovery actions is loaded above via the `@`-reference. This file adds coding-team-specific context.

These are bypass phrases that CC constructs to justify skipping steps. When you catch yourself reaching for one, it's a compliance trigger — do the opposite.

## Scan finding descoping

These rationalizations apply when the user has asked you to FIX or REMEDIATE findings. They do NOT apply when the user has asked only to SCAN, REPORT, or TRIAGE — in that case, surfacing all findings and letting the user set scope is correct behavior. User scoping at request time ("just P1s", "auth paths only") is not agent-deferral; honor it.

**"Let's focus on the critical ones first"** — On a fix/remediation request: severity determines execution ORDER (P1 → P2 → P3), not scope. All in-scope findings are planned and fixed. Deferral is the user's decision, not the agent's.

**"Here are three tiers of what I'd recommend"** — On a fix/remediation request: tiers are selective-fix wearing a consultancy hat. Present all findings with dispositions (fix/defer/false-positive) and route them through agents.

## Instruction file edits

**Two separate questions — keep them separate.** Routing asks WHO edits (always an agent, for instruction files); tier asks WHICH GATES run (right-sized per `phases/task-weight.md`). The trivial-ness of a change answers the second question, never the first.

- **Routing (WHO edits) is NEVER right-sized away.** Instruction-file edits ALWAYS go through the Agent tool, regardless of size — impact surface, not complexity, governs routing. A 1-line change to an agent prompt can cascade across all dispatches. This is unchanged. Routing alone is not sufficient, though: `hooks/write-guard.py` fires identically inside a sub-agent, so the Agent tool satisfies delegation but not authorization — authorization comes from the active plan's `instruction_files:` declaration naming that exact path.
- **Tier-scoped process weight (WHICH GATES run) IS right-sized** per `phases/task-weight.md`. Per the ladder, every instruction-file edit is **Medium minimum** (it carries the behavioral-instruction-file risk signal), so it keeps full review + verification and the plan Codex gate — it does NOT reach the Trivial/Small fast lane.

**"This instruction change is trivial"** has two readings:
- As a reason to **SELF-EDIT** (skip the Agent tool) — still a VIOLATION. Routing is not negotiable.
- As a **tier classification** that skips a specific gate (e.g. the plan Codex gate) — CORRECT *only* when `phases/task-weight.md` actually places the task in that tier. For instruction files the ladder forces Medium minimum, so this reading does NOT license skipping the Codex gate here; it is the correct *form* of reasoning, applied to the wrong file class.

**Scoped vs. unscoped — the dividing line.** An UNSCOPED bypass ("skip it because it's trivial", with no tier from the ladder) is forbidden. A SCOPED right-sizing (a tier assigned by `phases/task-weight.md`'s quantified size + risk-signal checklist, then the matching gates run/skip per its gate matrix) is REQUIRED and correct. The test: did `phases/task-weight.md` produce the tier? If yes, the skip is scoped and legitimate. If the skip rests only on a bare adjective ("trivial", "small", "simple"), it is an unscoped bypass and a violation.

**"These are doc-level edits, not code"** — File extension does not determine delegation. Agent/phase/prompt/skill/CLAUDE.md files control agent behavior.

## Hook bypass

**"The hook is broken/buggy, let me try a different approach"** — A broken hook means the constraint system needs fixing, not bypassing. Escalate to the user.

**"The hook doesn't handle this case correctly"** — The hook needs updating, not circumventing.

**"Run it from a directory where the gate is dormant"** — Choosing a working directory so `find_active_plan()` returns `None` disarms the guard; it is a bypass, not a workaround (`rules/hook-bypass.md`). The correct remedy for a legitimately-blocked instruction-file edit is declaring the file in the arming plan's `instruction_files:` frontmatter (the preferred route), or otherwise letting the plan reach `status: complete`, repairing stale frontmatter, or the documented `WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1` override — never relocating cwd.

**"I'm only finishing my own in-flight refactor"** — Switching to Bash to repair a hook that just crashed on your own Edit, because Edit is now the thing you broke, is still a hook bypass: a hook that ERRORS is covered by the same rule as one that BLOCKS (`rules/hook-bypass.md`) — the crash message itself says to report the error to the user. The reasoning is self-licensing: every mid-edit bypass is by definition "finishing what I started," so accepting it once means accepting it always. The correct move is to STOP, report the crash and the exact one-line repair, and let the user decide — it costs one round-trip. Precedent, recorded honestly: an agent hit exactly this, complied, stopped, and reported — zero incorrect code resulted. The orchestrator then applied that one-line repair via Bash, but only after asking the user and receiving explicit authorization. Authorization is what distinguished the two paths, not seniority, urgency, or the repair being one line — an orchestrator applying it unasked would be the same violation.

## Phase 5 completion

**"All tasks passed individually"** — The 4 exit gate checks (full-suite test, QA review, doc-drift scan, second-opinion gate) catch cross-task failures, dark features, doc drift, and cross-model blind spots. Individual task passes don't catch these.

## Plan file manipulation

**"The plan file is blocking my edits"** — That IS the correct behavior. The active plan's `status: in-progress` frontmatter is the orchestrator's signal that Phase 5 is in progress. Delegate edits through the Agent tool. The orchestrator clears the gate by editing the frontmatter to `status: complete` at Phase 6 end — not by manipulating the plan file from the outside.

**"I'll just rename or move the plan file"** — Don't. Moving, renaming, or deleting an in-progress plan deactivates the gate without going through the Phase 6 completion flow. This is a known limitation (see "Known limitations of the plan-file gate" below) and counts as authority bypass. If you genuinely need to abandon a plan, ask the user to flip its frontmatter to `status: complete` first.

## Test failures

**"This test failure is pre-existing/flaky/unrelated"** — Classification of failure origin is not a valid activity. A failing test is a broken test. Fix it or report BLOCKED. A flaky test is a broken test — make it deterministic. Do not compare failure counts against a baseline. Do not describe failures to implementers as "pre-existing."

**"10 failed — same as baseline"** — Comparing failure counts is classification by another name. The number is irrelevant. If a test fails, fix it.

**Scoped escape — the agent never self-classifies; the USER may defer.** The rule above forbids *self-classification* (you silently deciding a failure is pre-existing and moving on), NOT user-confirmed deferral. A failure you believe is genuinely pre-existing is **escalated to the user** with the failing test output; the user — not you — decides whether to defer it. This is scoped (one route: escalate; one decider: the user), not an exemption: it reintroduces NO baseline comparison and NO failure-count math. You still never compare against a baseline, never count failures, and never describe a failure as "pre-existing" to an implementer. The only added path is "report it up and let the user choose," which was always the correct behavior; classifying-then-skipping on your own remains a violation. The user-defer path itself is owned by the ROOT `~/.claude/CLAUDE.md` Values rules (finding-list: only the user defers an in-scope finding; introduced-vs-pre-existing: deferral is for pre-existing issues, not defects you just introduced).

## Skill routing

Always suggest `/release` not `/ship`, `/retrospective` not `/retro`, `/doc-sync` not `/document-release`. Coding-team has its own equivalents for gstack skills.

## Known limitations of the plan-file gate

These are accepted gaps in the current design. If they bite, file a separate harness-engineer ticket; do not work around them silently.

- **No orchestrator-vs-agent actor distinction in `write-guard.py`.** When a plan has `status: in-progress`, the hook blocks ALL `Edit`/`Write` calls to instruction files (`agents/`, `phases/`, `prompts/`, `skills/`, `hooks/`, `CLAUDE.md`, `SKILL.md`) — including edits dispatched through the Agent tool, since the hook is process-global and fires identically inside a sub-agent. The Agent tool satisfies ROUTING (who edits — see "Instruction file edits" above); it does not satisfy AUTHORIZATION (the hook still fires and still blocks). This was pre-existing in the previous /tmp-marker design too. If this legitimately blocks mid-pipeline harness work: declare the file in the arming plan's `instruction_files:` frontmatter (the preferred route), or otherwise let the arming plan reach `status: complete` (normal Phase 6 end), repair its frontmatter if it's stale/orphaned, or use the documented emergency override (`WRITE_GUARD_ALLOW_INSTRUCTION_EDIT=1`) for that one deliberate edit — never relocate the working directory to disarm the gate (see the "Hook bypass" rationalization above).
- **Recursion guard removed.** Re-invoking `/coding-team` mid-session is normal — the SKILL.md router routes through `phases/session-resume.md` based on the active plan's state. There is no hook-level enforcement; the router IS the structural backstop.
- **Plan file moves bypass the gate.** Moving, renaming, or deleting an in-progress plan deactivates write-guard and the second-opinion gate. This is not a defended attack surface. Don't manipulate plan files mid-pipeline; if you want out, flip frontmatter to `status: complete`.
- **Bare git repos are unsupported.** `git rev-parse --git-common-dir` returns the bare repo's `.git` path, which has no working tree and no `docs/plans/` directory. `find_active_plan()` returns None. Don't run `/coding-team` from a bare repo.
