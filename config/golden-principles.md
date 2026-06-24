# Golden Principles

Tiebreakers for ambiguous decisions. Referenced by any AI agent working in this codebase.

## 1. Real Over Mocks
Use real implementations in tests — see `rules/test-files.md` for the base rule. Only mock when a dependency is physically impossible to run locally: external paid API with no test mode (e.g. Stripe, Bittensor), hardware not in CI (e.g. GPU), or a local LLM / Ollama model not installed locally.
- **Enforcement**: write-guard's `check_no_mocks()` blocks mock patterns at Edit/Write time (PreToolUse hook, not a git hook)
- **Escape hatch**: `# mock-ok: <reason>` on the line

## 2. Repository Is Source of Truth
If it's not in the repo, it doesn't exist for agents. Architecture decisions, naming conventions, domain rules — commit them or lose them. Not Slack. Not Confluence. Not tribal knowledge.

## 3. Negative Rules Are Stronger
"NEVER do X" triggers avoidance. "Do Y" competes with training data. Pair every positive convention with a negative prohibition. Use NEVER and IMPORTANT markers for critical rules.

## 4. Progressive Disclosure
Root instruction files are maps, not manuals. Keep AGENTS.md under 100 lines. Keep CLAUDE.md under 200 lines. Point to `docs/` for depth. Agents load detail on demand via "Read when:" triggers.

## 5. Instruction Clarity Beats Model Capability
Across every case study — OpenAI, Stripe, Steinberger, Mercari, Spotify — the highest ROI came from clearer instructions, not better models. Detailed specs beat smart inference. Explicit examples beat implicit learning. Written rules beat training loops.

## 6. Observation Is Second-Highest Leverage
After constraint design, invest most heavily in observability. Task completion rate, iteration count, escalation rate, code quality scores. Monitor agent behavior, not just infrastructure health. The observation system determines what gets escalated to humans.

## 7. Verify Before Claiming Done
NEVER claim work is complete without running verification commands. Evidence before assertions. Run tests, linters, type checks — then report. An agent that passes all tests and skips edge cases has satisfied the letter, not the spirit.
- **Enforcement**: `git-safety-guard.py` blocks commits/pushes when tests/lint were not run; the `/verify` skill surfaces the checklist — no dedicated git hook or stamp mechanism exists for this

## 8. Bounded Iteration
If the same fix fails 3 times, STOP. Escalate to human with context: what you tried, what failed, what you think the problem is. Doom loops waste tokens, money, and context window.
- **Enforcement**: `loop-detection.py` IS registered as a PostToolUse/Bash hook (MAX_RETRIES=3) but is currently NON-FUNCTIONAL — it reads the wrong event key (`tool_result` at :142; the real key is `tool_response`) and PostToolUse never fires on a non-zero exit, so it observes no failures; honest repair is tracked as a deferred loop-detection finding (the mechanism fix is out of scope here)

## 9. Ask Before High-Impact Changes
Adding dependencies, modifying schemas, changing public APIs, deleting shared files — these affect the team and the project's long-term direction. Pause and confirm before proceeding.

## 10. Boring Technology Wins
Prefer composable, API-stable, well-represented-in-training-data tools. Agents perform better with technology they've seen extensively during training. Choose Express over a custom framework. Choose PostgreSQL over a niche database. Choose standard patterns over clever abstractions.

## 11. Consolidate Before Adding
NEVER create a new utility, helper, or pattern without first searching for an existing one. Check with code search tools before writing. Five date formatters instead of one is how entropy kills codebases. If a similar function exists, use it or extend it.

## 12. Self-Evolving Instructions
When you discover an undocumented convention through a failed test, linter error, or code review feedback — add it to AGENTS.md or CLAUDE.md. The best instruction files aren't written; they're grown from real friction.

## 13. Spec Before Code
Read or write the spec/plan before implementing. Understand what "done" looks like before writing the first line. If acceptance tests exist, read them first. If they don't, ask what "correct" means before guessing.

## 14. Don't Scope Creep Mid-Task
If you discover adjacent work while implementing, note it separately. NEVER expand the current task's scope without asking. Adding scope mid-task is the most common cause of agent confusion and incomplete work. Park the idea, finish the task, come back to it.

## 15. Error Messages Are Instructions
When writing error handling, include what the caller should do about it. Not just "failed" — why it failed and how to fix it. Every error message is an instruction file for whoever (human or agent) encounters it next.

## 16. Naming Is Architecture
Consistent naming conventions across the codebase are load-bearing, not cosmetic. When iOS calls it `lastPurchaseDate` and Android calls it `last_purchase_date`, translation is easy. When one uses `fetchUserProfile` and the other uses `getUserData`, everything breaks. Inconsistent names produce inconsistent agent output. Align names before aligning code.
