# Retrospective: Case Study Audit + Memory Revival

**PR:** #21
**Branch:** fix/case-study-audit-findings
**Date:** 2026-03-25

## What went well

- **Dual-agent audit was highly effective.** Running harness-engineer and prompt-craft auditors in parallel against the same 30-case checklist caught different classes of issues. Harness-engineer found structural gaps (hooks, settings). Prompt-craft found instruction quality gaps (YAML ordering, missing sections in prompts). Neither alone would have found all 8.
- **8 parallel implementers completed without conflicts.** Despite 3 agents touching ct-harden-auditor.md simultaneously (Case 16 + Case 25 + Case 8), all changes landed cleanly on different sections. Git's merge handled the sequential commits correctly.
- **Haiku-tier agents handled all 8 tasks.** Only the YAML reordering task (touching 5 files) needed sonnet. The rest were single-file mechanical edits that haiku completed in 20-35 seconds each.
- **Case studies as executable checklist validated.** The 30-case document functioned exactly as described in its meta-observation: fed into agent context, it becomes a systematic audit tool. Found a Case 28 recurrence that no one had noticed.
- **Memory revival closed a real gap.** The 27 consolidated rules were sitting on disk unused. Pruning the 12 promoted ones and wiring the remaining 15 + 30 case principles into the orchestrator makes them active again.

## What to improve

- **No audit loop on the 8 fixes.** Went straight from implementer output to PR without dispatching auditors. For CC instruction file changes, prompt-craft audit should have reviewed each edit. The risk: a haiku agent may have used slightly wrong framing in a CC instruction file that a prompt-craft auditor would catch.
- **Router hook wasn't deployed via deploy.sh.** The implementer updated both the repo copy and the deployed copy, but it did so manually (editing both files). Should use `scripts/deploy.sh` as the canonical deployment mechanism.
- **Pre-computed data not passed to implementers.** The audit agents generated detailed findings, but implementers received only the distilled fix spec — not the audit agent's full reasoning. For CC instruction files specifically, the "why" matters as much as the "what."

## Recurring patterns

- **Case 28 recurrence in production.** The Case 28 pattern (exemption accumulation) literally recurred in the router hook — the very pattern the case study documents. This validates running periodic case-study audits.
- **Multi-file edits on the same agent file.** ct-harden-auditor.md was touched by 3 separate tasks. This is a signal that the file accumulates changes from multiple failure modes — it may benefit from sectioning that groups related concerns.
- **Memory systems drift from active use.** The consolidated-feedback.md was comprehensive and current, but nothing loaded it. Systems that aren't wired into the pipeline decay into documentation.

## Metrics

- **Commits:** 10 total (8 fix, 1 memory rewrite, 1 SKILL.md wiring)
- **Files changed:** 12
- **Lines:** +127 / -54
- **Rework ratio:** 0/10 (no fix commits needed)
- **Parallel agents:** 8 implementers dispatched simultaneously
- **Wall-clock time:** ~15 minutes (audit) + ~5 minutes (implementation) + ~5 minutes (memory revival)
- **Model usage:** 2 opus (audit agents), 1 sonnet (YAML reorder), 7 haiku (other implementers)

## Action items

- [ ] Run prompt-craft audit on all 8 edited files in a follow-up session
- [ ] Add case-study audit to periodic maintenance checklist (every 5-10 PRs)
- [ ] Consider a hook that warns when memory/consolidated-feedback.md hasn't been read in a coding-team session
