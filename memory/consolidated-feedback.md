---
name: Consolidated behavioral rules and case study principles
description: Hard-won rules from feedback + 30 failure patterns from harness-debugging-case-studies — loaded at session start to prevent known failure modes
type: feedback
---

# Behavioral Rules (consolidated)

> Rules that exist only at the prompt level — no hook or rule-file enforcement. Promoted rules have been removed (see hooks/, rules/, and CLAUDE.md for structural enforcement).

1. Dispatch agent work BEFORE doing self-executable tasks (memory saves, doc writes). Agent work takes longer.
2. NEVER suggest /ship — always suggest /release. Same for /retrospective not /retro, /doc-sync not /document-release.
3. Agent teams when COORDINATION=yes. Subagents when independent work.
4. Use /prompt-craft audit before writing or modifying skill instructions.
5. Update symlinks in ~/.claude/skills/ when renaming or creating standalone skills.
6. List docs/plans/ directory first when resuming work — never guess filenames.
7. Direct embedding > propagation through intermediaries. Put tools in worker descriptions, not Team Leader instructions.
8. Codesight-mcp is preferred for code analysis when available. Reindex stale indexes. Grep/Read are fallbacks when MCP is unavailable or calls fail.
9. CI failures require classification before action. Non-code failures (infra/billing/permissions) go to the user immediately — NEVER attempt code fixes.
10. When a background CI watcher completes, read its output before dismissing. "Already handled" is a rationalization — read the log, then decide.
11. Never retry a failed MCP tool more than once. Mark it unavailable for the session, degrade to built-in tools (Glob, Grep, Read). "Maybe it's back up now" — it isn't.
12. Run multi-pass audits with distinct focus per pass: (1) agent-internal, (2) cross-file consistency, (3) behavioral executability, (4) migration residue. Stop when a pass comes back clean.
13. Subagent prompts must explicitly override inherited CLAUDE.md rules that conflict with the subagent's role. Agents cannot infer exemptions from context.
14. Do not pause for user confirmation between severity phases during scan-fix workflows. Print a progress summary, then continue automatically. User has Esc to interrupt.
15. When diagnosing behavioral issues, try identity framing and named rationalizations first (prompt-craft tiers 1-2). Only escalate to prohibitions and restructuring if those don't hold.
16. Delegation is the default, not a choice. Do NOT offer self-execution as an option ("should I just execute directly?"). Spec clarity determines model tier (haiku vs sonnet), not whether to delegate. Named rationalization: "the spec is already clear."

## Case Study Principles

> From harness-debugging-case-studies.md — 30 failure patterns and their fixes.

1. **Permission language** — Scattered "skip/directly/simple" lines compound into escape hatches. One exemption, one location, explicit scope. (Case 1)
2. **Category gaps** — Rules covering one category ("test failures") leave adjacent categories ("review findings") unblocked. Write rules for intent, not instance. (Case 2)
3. **Split-audience files** — One instruction file serving two roles (orchestrator + worker) serves neither well. Split by audience, progressive disclosure. (Case 3)
4. **Format-vs-function** — Define exceptions by purpose (documentation vs config), not format (.md). Agents classify ambiguously in whichever direction is easier. (Case 4)
5. **Context inheritance** — Shared reference files (style guides, principles, memory) must be audited as a matrix: agents × files. Every code-touching agent needs the style guide. (Case 5)
6. **Serialization anti-pattern** — Agents do easy self-tasks first. Rule: dispatch long-running work first, lightweight work second. (Case 6)
7. **Rationalization override** — When rules are explicit and agent still bypasses, name the specific rationalization and make it a compliance trigger. (Case 7)
8. **Tool reversion** — Agents revert to trained defaults (Read/Grep/Bash) under pressure. Frame new tools as primary, trained tools as fallback. First-mentioned wins. (Case 8)
9. **Structural demotion** — Tools in a separate "Additional" section are treated as optional. Colocate all mandatory items in the same block. Separation = demotion. (Case 9)
10. **Silent drop** — Agents can't self-verify completeness. External verification with hard count from dispatcher is the only reliable pattern. (Case 10)
11. **Competing namespace** — When multiple skill frameworks coexist, explicitly prohibit competing commands by name. Agent follows the structurally louder signal. (Case 11)
12. **Filename guessing** — After context loss, agents must discover filesystem state by listing, not inference. Never construct expected filenames. (Case 12)
13. **Task misclassification** — Content controlling agent behavior is prompt engineering regardless of format. Route CC instruction file edits through /prompt-craft. (Case 13)
14. **Infrastructure orphan** — Tasks with side effects beyond files (symlinks, env vars, configs) must list those side effects explicitly. Agents don't know about operational dependencies. (Case 14)
15. **Friction mismatch** — Auto-continue at progress points, pause only at genuine decision points. User has Esc. (Case 15)
16. **Cross-layer propagation** — Fixes at the orchestrator layer must propagate to every worker prompt that encounters the same category. Audit fixes across the full dispatch chain. (Case 16)
17. **Missing branch policy** — "Always use feature branches" feels too obvious to state. It isn't. Encode every workflow assumption explicitly. (Case 17)
18. **Propagation failure** — Every indirection layer between instruction and executor is lossy. Embed tools directly in each worker's description. Direct > propagation. (Case 18)
19. **Recursive invocation** — Global routing rules leak into worker contexts. Workers need identity statements overriding global rules: "You ARE the delegate." (Case 19)
20. **Severity downgrade** — Tool severity tiers (warning/error) become inaction justification. Override tool classification explicitly: "We treat warnings as errors." (Case 20)
21. **Orphaned resource** — Workflows creating external resources (PRs, infra) need cleanup paths for session abandonment: retry cap + cleanup + session-resume detection. (Case 21)
22. **Structure-not-behavior tests** — Agents write tests that read source files and check strings. Require behavioral assertions: call function, assert output. (Case 22)
23. **Unpropagated fix** — Fixing one instance doesn't fix the class. After fixing a vulnerability, search for the same pattern at all analogous sites. (Case 23)
24. **Context saturation** — Beyond ~300-400 lines, MANDATORY labels stop working. Fix structurally: required output fields, checkpoints at headroom layer, pre-computation. (Case 24) *(enforced by hook: hook-health-check.py — instruction files >200 lines)*
25. **Incomplete refactor** — Add new pattern, verify it works, REMOVE the old pattern. Skipping step 3 creates contradictory instructions. (Case 25)
26. **Tool overload** — 21 tools in one prompt creates selection ambiguity. Cap at 5-6 primary tools, pre-compute results from secondary tools at orchestrator level. (Case 26)
27. **Trust inversion** — Verification gates defaulting to trust are decoration. Invert: verify always, skip under narrow explicit conditions. (Case 27)
28. **Exemption accumulation** — Same permission in multiple places amplifies beyond intended scope. One exemption, one canonical location, explicit scope boundary. (Case 28)
29. **Configuration drift** — Agent capabilities defined in two places will drift. Establish single source of truth for dispatch type. (Case 29)
30. **Identity reframe** — When enforcement escalates through multiple rounds, the problem is misaligned identity. Reframe so desired behavior is what the agent's self-model wants. (Case 30)
31. **User-specified path override** — User instructions are directives, not suggestions. When the user specifies a path/name/value, execute it — don't evaluate whether a "better" alternative exists. Named rationalization: "content suggests a better path." (Case 31)
32. **Asymmetric set/clear** — Lifecycle pairs (set/clear, acquire/release) must use identical criteria. If the "set" is conditional on skill name, the "clear" must check the same condition. Broad clear + narrow set = silent state corruption. (Case 32)
33. **Stale calibration constants** — Hardcoded constants in hooks encode environmental assumptions. When the environment changes (model upgrade, config change), constants become wrong silently. Audit constants against current reality, not just logic against spec. (Case 33)
34. **Scaffold without activation** — A hook registered and deployed but missing its runtime state producer is a no-op through graceful degradation. Test the full activation chain: state producer → hook reads → hook acts. Ship activation with scaffold. (Case 34)
35. **Adversarial path inputs** — Path-based allowlists using string operations (`in`, `startswith`) are bypassable via substring collisions. Use structural path APIs (`Path.parts`, `is_relative_to`). Adversarial review catches input classes the author's mental model doesn't include. (Case 35) *(enforced by hook: write-guard.py — path safety advisory)*
36. **Warn→block escalation** — If a hook warning is routinely ignored under context pressure, escalate from `allow` (inform) to `block` (constrain). The question isn't "is this too aggressive?" but "does the warning prevent the failure?" If not, it's decoration. (Case 36)
37. **Enumerated item completion** — Agents process ~50% of enumerated items (files to modify, hooks to migrate) then report DONE. Named rationalizations: "The pattern is established, remaining items follow the same approach" and "I've done the representative ones." Fix: explicit item count in dispatch, count verification by orchestrator, named rationalizations in implementer prompt. (Case 37)
38. **Selective-fix costumes (advisor-mode rationalization)** — Selective-fix has four costumes: P1-only, P3-deferral, critical-first, and advisor-mode. Tiered recommendations and "what I'd skip" lists are selective-fix wearing consultancy clothes. Name all variants. (Case 41)
39. **Second-opinion gate skip** — Inform-verb enforcement degrades under context pressure. Any gate that matters needs a Verify-verb checkpoint — a structural check that blocks progression if the gate was skipped. (Case 42)
40. **Hook bypass rationalization** — Hooks are not obstacles. If a hook blocks, comply. If a hook errors, STOP and report. Never work around a hook — "the hook is broken" is a bypass rationalization, not permission. (Case 43)
41. **Hooks fail-open** — Safety-critical hooks must fail-closed. Wrap main() in try/except that outputs a block decision on ANY exception. A hook that crashes and allows is worse than no hook — it creates false confidence. (Case 44)
42. **Session file deletion** — A guard is only as strong as its dependencies. If the guard depends on a deletable file, protect that file. When you fix a guard, ask: "Can an agent remove what the guard depends on?" (Case 45)
