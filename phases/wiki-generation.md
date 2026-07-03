# Wiki Article Generation

> Loaded by the orchestrator from `phases/completion.md` (Phase 6) when the tier gate below is satisfied. Return to completion.md's Decision Log section after this section completes or is skipped.

**Tier gate (evaluate BEFORE prompting the user):**
- **Effective Trivial:** SKIP wiki generation entirely. Proceed to Decision Log.
- **Effective Small:** SKIP wiki generation UNLESS the completion summary contains at least one recurring pattern. If the summary is empty or has no patterns, skip and proceed to Decision Log. The user may still opt in by saying "write wiki article."
- **Effective Medium/Large:** Offer wiki generation below.
- **Empty summary:** SKIP wiki generation regardless of tier — the wiki populates from the summary; an empty summary produces a meaningless article. The user may opt in explicitly.

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
