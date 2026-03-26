---
name: prompt-craft
description: "Write or audit Claude Code SKILL.md files, CLAUDE.md instructions, and agent prompt templates — CC-specific patterns like named rationalizations, identity framing, tool naming, and threshold quantification. Also diagnoses CC behavioral issues ('CC keeps doing X', 'CC ignores my instructions'). For general LLM API prompts (system prompts, few-shot, structured output), use /prompt-engineer instead."
---

# /prompt-craft — Skill & Prompt Engineering

When invoked standalone:
- Create a new skill: start at **Create**
- Fix a behavioral issue ("CC keeps doing X"): start at **Diagnose**
- Improve an existing skill or prompt: start at **Audit**
- Update the skill taxonomy: start at **Taxonomy**

When invoked from /coding-team Phase 2: the Team Leader provides scope. Read `skills/prompt-craft/phase2-worker.md` for the Phase 2 lens.

---

## Create — New Skill from Scratch

### 1. Clarify purpose
- What specific behavior should this skill produce?
- When should CC invoke it? When should it NOT?
- Standalone skill or pipeline phase? Context budget?

### 2. Write frontmatter

The `description` field controls when CC invokes the skill:
- Start with "Use when..." — CC pattern-matches on this
- Include trigger phrases and negative triggers ("Do NOT use when...")
- Be specific: "Use when investigating a bug or test failure" not "Use for code tasks"
- Keep under 3 sentences

```yaml
---
name: skill-name
description: "Use when [trigger]. [What it does]. [Do NOT use when...]."
---
```

### 3. Write the body

Structure: **Identity preamble** (what the agent IS — identity determines behavior more reliably than prohibitions) → **Standalone preamble** (bootstrap when invoked directly vs pipeline) → **Core protocol** (imperative commands) → **Decision points** (if/then routing) → **Red flags** (what to never do) → **Verification** (how to confirm correct behavior).

### 4. Language rules

Seven patterns (full examples in `skills/prompt-craft/language-rules.md`):

1. **Framing determines defaults** — desired path first, fallback second
2. **Name tools explicitly** — `Agent tool`, not "dispatch agents"
3. **Prohibitions must be explicit** — CC doesn't infer what not to do
4. **Identity over prohibition** — "you are the orchestrator" beats "NEVER write code"
5. **Name the rationalization** — turn bypass phrases into compliance triggers
6. **Quantify thresholds** — "8+ files" not "large tasks"
7. **Tables beat prose for routing** — classification tables for multi-path decisions

### 5. Test the skill

Evaluate with the audit checklist (see Audit section below).

### 6. Agent Template (standard 14-step structure)

1. Frontmatter  2. Dispatch Context  3. Identity Block  4. Pipeline Isolation  5. MANDATORY block  6. Core Protocol  7. Code Intelligence table  8. MCP Resilience block  9. Project-Specific Criteria slot  10. Calibration  11. When You Cannot Complete  12. Finding Integrity  13. Named Rationalizations  14. Output Format

See `skills/prompt-craft/patterns-catalog.md` for templates of steps 8, 11, 12, and 13.

---

## Diagnose — Why CC Isn't Following Instructions

When a user reports "CC keeps doing X instead of Y":

### Step 1: Identify the instruction
Find the exact line that should produce behavior Y. If it doesn't exist, the fix is adding it.

### Step 2: Check framing

| Symptom | Fix |
|---|---|
| CC uses the wrong tool | Name the correct tool explicitly with exact syntax; put it first in conditionals |
| CC skips a step | Make mandatory: "MUST", "ALWAYS", "before proceeding" |
| CC does the opposite | Flip the default — desired behavior first, exception second |
| CC half-follows instructions | Separate imperative instructions from explanatory prose |
| CC follows spirit but not letter | Replace "should"/"consider"/"try to" with "MUST"/"DO"/"ALWAYS" |
| CC ignores instructions late in conversation | Shorten skill, move details to on-demand files, repeat critical rules at decision points |
| CC defaults to subagents over agent teams | Put agent teams path first in framing |
| CC writes code when it should delegate | Add "NEVER use Edit/Write directly. Spawn an agent." |
| CC constructs category exceptions | Name the rationalization as a compliance trigger |
| CC dismisses background task output | Add "read output FIRST, then classify" — name "already handled" as rationalization |
| CC obeys reluctantly, finds new bypasses | Rewrite as identity framing, not prohibition |
| CC freezes after prohibition | Add "Instead, do Y" after every "NEVER do X" |
| CC processes some list items but not all | Add item count at dispatch + orchestrator count verification |
| CC ignores rules late in long conversations | Front-load critical rules in top 100 lines; add required output fields |

### Step 3: Check competing instructions
- Does another skill or CLAUDE.md give conflicting guidance?
- Does the main SKILL.md say one thing but a phase file say another?
- Does a prompt template override the skill's instructions?

### Step 4: Propose fix

Prefer (in order): 1. **Name the rationalization** 2. **Identity framing** 3. **Decision table** 4. **Explicit prohibition** 5. **Reframing a conditional** 6. **Restructuring content** (most expensive, for context pressure only)

### Step 5: Write a memory file

If recurring, create `memory/feedback-<slug>.md` with: what CC does wrong, why (root cause), how to apply (the fix as an instruction).

### Step 6: Verify the fix held
In the next session: did the agent follow the instruction? Find a new bypass? If held, note in memory file. If bypassed, escalate to next fix tier.

---

## Audit — Evaluate an Existing Skill or Prompt

Read the file completely, then evaluate. For standard block templates, see `skills/prompt-craft/patterns-catalog.md`.

### Behavioral alignment
- [ ] Frontmatter `description` accurately describes triggers? No false positives/negatives?
- [ ] Desired default behavior stated first in every conditional?
- [ ] All tool names explicit? Prohibitions explicit?
- [ ] Foundational boundaries use identity framing, not prohibition?
- [ ] Known rationalizations named as compliance triggers?

### Context efficiency
- [ ] Could sections move to on-demand files? Rare-situation sections extracted?
- [ ] Critical instructions near the top? Works under tight context?

### Clarity for CC
- [ ] Thresholds quantified? Decision points have explicit routing (tables/if-then)?
- [ ] Rationale separated from instruction?

### Standard blocks
- [ ] Enumerated-item-completion protection? Replacement behaviors for prohibitions?
- [ ] Under 200 lines? "When You Cannot Complete" block? Finding Integrity block?
- [ ] Escalation paths explicit (BLOCKED, NEEDS_CONTEXT)?

### Prompt template quality (`prompts/*.md`)
- [ ] Tells agent what it IS and what it is NOT?
- [ ] Full context provided? Output format specified? Failure handling?

### Report format
```
AUDIT: [skill/prompt name]
PASS: [what's working well]
ISSUES: [severity] [issue]: [current text] -> [suggested fix]
CONTEXT: Current N lines, Recommended N lines (move X to on-demand)
```

---

## Taxonomy — Skill Discovery Maintenance

For taxonomy operations (adding/removing skills, auditing the taxonomy), read `skills/prompt-craft/taxonomy.md`.
