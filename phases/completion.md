# Phase 6: Completion

## Pre-check: Second-Opinion Gate

The lifecycle hook enforces this gate by reading the active plan file's Completion Checklist. Before proceeding with Phase 6, ensure `phases/post-execution-review.md` has been followed and the plan's `- [ ] Second-opinion review` line is now `- [x]` (or contains `skip: <reason>`). If it isn't, the hook will block at pipeline completion regardless — load post-execution-review.md and complete it first.

Known rationalization: "We already reviewed everything in the audit loop" — audit loop review is internal (same model reviewing its own work). Second-opinion is cross-model validation and serves a fundamentally different purpose. They are not substitutes for each other.

---

After all tasks are executed and verified:

1. **Run full test suite** — independent verification required even if Phase 5 passed, because context may have been cleared between phases and additional commits may have landed (fresh output required)
2. **Run linter** — verify clean output
3. **Determine base branch:**
   ```bash
   git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null
   ```

4. **Pre-gate deliverable check:** Before presenting completion options, verify these deliverables exist:

| Deliverable | Check | If missing |
|-------------|-------|------------|
| All tests pass | Fresh test run output in this message | Run tests now |
| Linter clean | Fresh lint output in this message | Run linter now |
| Plan tasks complete | All tasks in plan have commits or explicit skip rationale | List gaps |
| Feature branch exists | Not on main/master | Cannot proceed — create branch first |

Produce any missing deliverables before opening the gate. Max 2 attempts per missing item, then warn the user and proceed anyway.

5. **Present options:**

```
Implementation complete. All tests pass. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work

Which option?
```

6. **Execute choice:**
   - **Merge locally:** checkout base -> pull -> merge -> verify tests on merged result -> delete feature branch -> cleanup worktree if applicable
   - **Push and create PR:** push -> create PR with summary and test plan -> follow the **CI Fix Protocol** below.
     Do NOT leave a failing-CI PR open without explicit user choice. If the user does not respond (session ending, context above 80%), close the PR and delete the branch: `gh pr close --delete-branch`. An orphan PR with failing CI generates email noise indefinitely.
   - **Keep as-is:** report branch name and worktree path, done
   - **Discard:** require user to type "discard" to confirm -> delete branch -> cleanup worktree

**Never** proceed with failing tests, merge without verifying, delete work without confirmation, or dismiss failures/findings as "pre-existing" or "not our problem." A bug is a bug regardless of when it was introduced.

7. **Final: mark plan complete.** After the user has selected and executed a completion option (merge/PR/keep/discard), edit the active plan file's frontmatter using the Edit tool: change `status: in-progress` to `status: complete`. This deactivates the write-guard and lifecycle gates for any future Phase 5 work in this repo.

   If the user chose `discard` and the plan file was removed as part of cleanup, this step is moot. If the plan file persists (any of merge/PR/keep, or discard that left the plan file in place), it MUST be marked `status: complete` before the session ends — leaving a plan with `status: in-progress` will block the next pipeline run with an ambiguous-active-plan error.

   Verify: re-read the plan, confirm `status: complete` is present in the frontmatter block.

## Pre-Push Verification

Before running `git push`, verify locally:

1. Run the project's full test command — all tests must pass
2. Run the project's lint command — must be clean
3. Run type checking if the project uses it — must pass

If ANY fail: dispatch an implementer via Agent tool to fix before pushing. Do NOT push hoping CI will be different from local results.

## CI Fix Protocol

When CI fails, read `phases/ci-fix-protocol.md` and follow its instructions. Key rules: read full logs, classify before acting, NEVER fix infra/billing issues with code changes, paste verbatim errors to implementers. Max 3 code-fix attempts.

## Learning Loop (Completion Summary)

After all tasks, produce a summary that includes audit findings across all rounds:

```
## Completion Summary

**Audit rounds:** N of 3 max
**Exit reason:** clean audit | low-only round | loop cap

### Recurring patterns
- [pattern]: appeared N times across rounds, severity, resolution
- [pattern]: ...

### Unresolved (low severity, deferred)
- [finding]: reason deferred

### Out-of-scope observations
- [anything auditors flagged outside the task scope]
```

Recurring patterns are the signal — if the same finding type appears across multiple tasks or rounds, it indicates a systemic issue worth noting for future work.

**Persistence:** The completion summary is incorporated into the retrospective document when the user runs `/retrospective`. If the user skips the retrospective, save the completion summary as a standalone file: determine `$REPO_ROOT` via `git rev-parse --show-toplevel`, create `$REPO_ROOT/docs/retros/` if needed using Bash tool (`mkdir -p`), and write the summary to `$REPO_ROOT/docs/retros/YYYY-MM-DD-<feature-slug>-completion.md` using the Write tool. Do NOT skip saving — completion summaries contain audit patterns that inform future planning.

## Harness Metrics Capture

After producing the completion summary, append a structured metrics line to `~/.claude/harness-metrics.jsonl` via Bash:

```bash
echo '{"date":"YYYY-MM-DD","project":"<repo-name>","task":"<feature-slug>","phases_used":["design","plan","execute","audit","complete"],"agents_dispatched":{"builder":N,"reviewer":N,"qa":N,"harden":N,"simplify":N,"prompt":N},"audit_rounds":N,"audit_exit":"clean|low-only|cap","findings_total":N,"findings_fixed":N,"findings_deferred":N,"rework_iterations":N,"test_pass_first_try":true|false,"ci_pass_first_push":true|false,"second_opinion":"ran|skipped|unavailable","elapsed_phases":{"design":"Nm","plan":"Nm","execute":"Nm","audit":"Nm"}}' >> ~/.claude/harness-metrics.jsonl
```

Fill values from this session's actual data. Use `null` for values you can't determine. Do NOT fabricate — `null` is better than a guess.

**Why:** This data feeds `/harness-retro` for evidence-based pipeline optimization. See Meta-Harness (arXiv:2603.28052) — raw execution data enables causal reasoning about harness failures. Summaries don't.

## Wiki Article Generation

**Skip if user chose "Discard this work."**

After producing the completion summary, generate a project learnings article for the vault wiki.

**Step 1: Determine topic.**
Read `~/Documents/obsidian-vault/AI/wiki/_master-index.md` using the Read tool. Based on the feature's domain, suggest the best-fit topic first, then present the full menu for confirmation or change:

```
Wiki article for this feature. Suggested topic: {best-fit}

1. ai-agents — Autonomous agent architectures
2. ai-coding-tools — CLI tools and code intelligence
3. ai-data-tools — Federated query engines and data-aware LLM infra
4. rag — Retrieval-Augmented Generation techniques
5. security — AI-augmented security tools
6. New topic (I'll specify)
7. Skip wiki article

Topic? (number or name)
```

- If user picks 1-5: use that topic directory.
- If user picks 6: ask for topic name and description. Create directory with Bash tool (`mkdir -p`). Create `_index.md` using the Write tool:
  ```markdown
  # {Topic Name}

  > Part of [[_master-index]]

  {One-sentence description}

  ## Articles

  | Article | Description |
  |---------|-------------|
  ```
  Add row to the `## Topics` table in `_master-index.md`:
  `| [[{topic-slug}/_index|{Topic Name}]] | {description} |`
- If user picks 7: skip wiki generation, proceed to Decision Log.

**Step 2: Generate article.**
Content comes from the completion summary already produced. Do NOT re-analyze the codebase. If the completion summary lacks decisions or patterns, ask the user: "Any key decisions or patterns worth noting? (or 'none')"

Write to `~/Documents/obsidian-vault/AI/wiki/{topic}/{slug}.md` using the Write tool:

```markdown
# {Feature Name}

> Part of [[{topic}/_index|{Topic Name}]]

{1-paragraph summary from completion summary}

## Key Takeaways

- {From completion summary recurring patterns or user-provided decisions}
(Omit section if no meaningful takeaways)

## Patterns

- **{Pattern}**: {description, when to reuse}
(Omit section if no patterns emerged)

## Retrospective

- What went well: {from completion summary}
- What to improve: {from deferred/unresolved items}
(Omit section if no retrospective data)

## Related

- [[{other wiki articles in same topic, if any}]]
```

**Step 3: Update topic index.**
Read the topic's `_index.md` using the Read tool. Find the `## Articles` table. Append a new table row:
`| [[{topic}/{slug}|{Feature Name}]] | {one-line description} |`

Known rationalization: "This project isn't wiki-worthy" — the user decides via the skip option, not the agent.

## Decision Log

After producing the completion summary, check whether any architectural or design decisions were made during this feature that should be recorded for future sessions.

**Prompt the user:**

> Were any architectural or design decisions made during this feature? (e.g., "chose X over Y because Z", "this API uses polling not webhooks because...", "we keep the old table for backward compat until...")
>
> If yes, I'll write a decision record to `memory/decisions/`.

**If the user provides decisions**, write each to `memory/decisions/YYYY-MM-DD-<slug>.md` using the Write tool:

```markdown
---
name: [decision title]
description: [one-line summary]
type: project
---

## Context
[What situation prompted this decision]

## Decision
[What was chosen]

## Alternatives Considered
- [Alternative] — rejected because [reason]

## Constraints
[Organizational, technical, or relationship factors]

## Consequences
[What would break if reversed without understanding why]
```

**Also persist to ContextKeep:** After writing the decision file, use `mcp__context-keep__store_memory` to store the decision with key `decision-<slug>` and the decision content as the value. This makes decisions searchable by the planning worker via `mcp__context-keep__search_memories` in future sessions. If ContextKeep is not available (MCP server not running), skip and note in status: 'ContextKeep not available — skipped' — the file-based approach is the primary record.

**If the user says no or skips**, proceed to Session Complete. Do NOT generate decisions the user didn't identify — this captures human organizational knowledge, not agent observations.

Read `phases/memory-nudge.md` and follow its instructions.

---

## Session Complete

After the user chooses a completion option and it's been executed, print this block VERBATIM (substitute actual branch name and chosen option):

> ---
>
> **Feature complete.** Branch: `<branch>` | Option: `<chosen option>`
>
> **Recommended next steps:**
>
> 1. `/retrospective` — engineering retrospective (commit patterns, test health, shipping velocity, what to improve). Saves to `docs/retros/` with eval feed-forward to `docs/project-evals.md`. Use coding-team's `/retrospective`, NOT gstack's `/retro` — they are different skills.
> 2. `/doc-sync` — update README, ARCHITECTURE, CLAUDE.md to match the shipped code
> 3. `/prompt-craft audit` — if this feature changed any skills, prompts, or CLAUDE.md, verify they still trigger correctly
>
> **If you chose "Push and create PR" and want a more automated release:** Run `/release` — it syncs main, runs tests, audits coverage, pushes, and creates the PR with coverage stats.
>
> **Starting something new?** `/clear` then `/coding-team` with your next task. If it's an unfamiliar codebase, start with `/onboard` for a guided orientation.
>
> ---
