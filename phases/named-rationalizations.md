# Named Rationalizations — Coding Team

@~/.claude/rules-on-demand/failure-taxonomy.md

**Cross-reference:** The consolidated taxonomy with recovery actions is loaded above via the `@`-reference. This file adds coding-team-specific context.

These are bypass phrases that CC constructs to justify skipping steps. When you catch yourself reaching for one, it's a compliance trigger — do the opposite.

## Scan finding descoping

**"Let's focus on the critical ones first"** — Severity determines execution order, not scope. P1 goes first, but P3 still gets fixed. All findings are planned and executed by default. Deferral is the user's decision, not the agent's.

**"Here are three tiers of what I'd recommend"** — Tiers are just selective-fix wearing a consultancy hat. Present all findings with dispositions (fix/defer/false-positive) and route them through agents. The default is ALL findings, ALL fixes.

## Instruction file edits

**Two separate questions — keep them separate.** Routing asks WHO edits (always an agent, for instruction files); tier asks WHICH GATES run (right-sized per `phases/task-weight.md`). The trivial-ness of a change answers the second question, never the first.

- **Routing (WHO edits) is NEVER right-sized away.** Instruction-file edits ALWAYS go through the Agent tool, regardless of size — impact surface, not complexity, governs routing. A 1-line change to an agent prompt can cascade across all dispatches. This is unchanged.
- **Tier-scoped process weight (WHICH GATES run) IS right-sized** per `phases/task-weight.md`. Per the ladder, every instruction-file edit is **Medium minimum** (it carries the behavioral-instruction-file risk signal), so it keeps full review + verification and the plan Codex gate — it does NOT reach the Trivial/Small fast lane.

**"This instruction change is trivial"** has two readings:
- As a reason to **SELF-EDIT** (skip the Agent tool) — still a VIOLATION. Routing is not negotiable.
- As a **tier classification** that skips a specific gate (e.g. the plan Codex gate) — CORRECT *only* when `phases/task-weight.md` actually places the task in that tier. For instruction files the ladder forces Medium minimum, so this reading does NOT license skipping the Codex gate here; it is the correct *form* of reasoning, applied to the wrong file class.

**Scoped vs. unscoped — the dividing line.** An UNSCOPED bypass ("skip it because it's trivial", with no tier from the ladder) is forbidden. A SCOPED right-sizing (a tier assigned by `phases/task-weight.md`'s quantified size + risk-signal checklist, then the matching gates run/skip per its gate matrix) is REQUIRED and correct. The test: did `phases/task-weight.md` produce the tier? If yes, the skip is scoped and legitimate. If the skip rests only on a bare adjective ("trivial", "small", "simple"), it is an unscoped bypass and a violation.

**"These are doc-level edits, not code"** — File extension does not determine delegation. Agent/phase/prompt/skill/CLAUDE.md files control agent behavior.

## Hook bypass

**"The hook is broken/buggy, let me try a different approach"** — A broken hook means the constraint system needs fixing, not bypassing. Escalate to the user.

**"The hook doesn't handle this case correctly"** — The hook needs updating, not circumventing.

## Phase 5 completion

**"All tasks passed individually"** — The 4 exit gate checks (full-suite test, QA review, doc-drift scan, second-opinion gate) catch cross-task failures, dark features, doc drift, and cross-model blind spots. Individual task passes don't catch these.

## Plan file manipulation

**"The plan file is blocking my edits"** — That IS the correct behavior. The active plan's `status: in-progress` frontmatter is the orchestrator's signal that Phase 5 is in progress. Delegate edits through the Agent tool. The orchestrator clears the gate by editing the frontmatter to `status: complete` at Phase 6 end — not by manipulating the plan file from the outside.

**"I'll just rename or move the plan file"** — Don't. Moving, renaming, or deleting an in-progress plan deactivates the gate without going through the Phase 6 completion flow. This is a known limitation (see "Known limitations of the plan-file gate" below) and counts as authority bypass. If you genuinely need to abandon a plan, ask the user to flip its frontmatter to `status: complete` first.

## Test failures

**"This test failure is pre-existing/flaky/unrelated"** — Classification of failure origin is not a valid activity. A failing test is a broken test. Fix it or report BLOCKED. A flaky test is a broken test — make it deterministic. Do not compare failure counts against a baseline. Do not describe failures to implementers as "pre-existing."

**"10 failed — same as baseline"** — Comparing failure counts is classification by another name. The number is irrelevant. If a test fails, fix it.

**Scoped escape — the agent never self-classifies; the USER may defer.** The rule above forbids *self-classification* (you silently deciding a failure is pre-existing and moving on), NOT user-confirmed deferral. A failure you believe is genuinely pre-existing is **escalated to the user** with the failing test output; the user — not you — decides whether to defer it. This is scoped (one route: escalate; one decider: the user), not an exemption: it reintroduces NO baseline comparison and NO failure-count math. You still never compare against a baseline, never count failures, and never describe a failure as "pre-existing" to an implementer. The only added path is "report it up and let the user choose," which was always the correct behavior; classifying-then-skipping on your own remains a violation.

## Skill routing

Always suggest `/release` not `/ship`, `/retrospective` not `/retro`, `/doc-sync` not `/document-release`. Coding-team has its own equivalents for gstack skills.

## Known limitations of the plan-file gate

These are accepted gaps in the current design. If they bite, file a separate harness-engineer ticket; do not work around them silently.

- **No orchestrator-vs-agent actor distinction in `write-guard.py`.** When a plan has `status: in-progress`, the hook blocks ALL `Edit`/`Write` calls to instruction files (`agents/`, `phases/`, `prompts/`, `skills/`, `hooks/`, `CLAUDE.md`, `SKILL.md`) — including legitimate edits dispatched through the Agent tool. The "delegate via Agent tool" rule is enforced by orchestrator instructions, not by the hook. This was pre-existing in the previous /tmp-marker design too. Workaround: harness work on coding-team itself runs from a parent directory whose `docs/plans/` is empty (e.g., `~/.claude/plans/` is not a git repo, so `find_active_plan()` returns None when invoked from there).
- **Recursion guard removed.** Re-invoking `/coding-team` mid-session is normal — the SKILL.md router routes through `phases/session-resume.md` based on the active plan's state. There is no hook-level enforcement; the router IS the structural backstop.
- **Plan file moves bypass the gate.** Moving, renaming, or deleting an in-progress plan deactivates write-guard and the second-opinion gate. This is not a defended attack surface. Don't manipulate plan files mid-pipeline; if you want out, flip frontmatter to `status: complete`.
- **Bare git repos are unsupported.** `git rev-parse --git-common-dir` returns the bare repo's `.git` path, which has no working tree and no `docs/plans/` directory. `find_active_plan()` returns None. Don't run `/coding-team` from a bare repo.
