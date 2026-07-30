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
Read `~/Documents/obsidian-vault/AI/wiki/_master-index.md` using the Read tool. Based on the feature's domain, SELECT the best-fit topic and proceed with it — do not present a menu. The index is readable and the article is editable, so a confirmation here only stalls the phase. Print one line naming the topic chosen:

```
Wiki article filed under: {topic}
```

Existing topics include `ai-agents` (autonomous agent architectures), `ai-coding-tools` (CLI tools and code intelligence), `ai-data-tools` (federated query engines and data-aware LLM infra), `rag` (retrieval-augmented generation), and `security` (AI-augmented security tools) — read `_master-index.md` for the live list rather than trusting this one.

- If an existing topic fits: use that topic directory.
- If no existing topic fits: name a new topic yourself from the feature's domain. Create the directory with the Bash tool (`mkdir -p`). Create `_index.md` using the Write tool:
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
The tier matrix in `phases/task-weight.md` decides whether a wiki article runs at all — there is no per-run skip option to offer.

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

Known rationalization: "This project isn't wiki-worthy" — the tier matrix in `phases/task-weight.md` decides that, not the agent's taste.
