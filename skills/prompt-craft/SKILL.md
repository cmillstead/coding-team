---
name: prompt-craft
description: "Write or audit Claude Code SKILL.md files, CLAUDE.md instructions, and agent prompt templates — CC-specific patterns like named rationalizations, identity framing, tool naming, and threshold quantification. Also diagnoses CC behavioral issues ('CC keeps doing X', 'CC ignores my instructions'). For general LLM API prompts (system prompts, few-shot, structured output), use /prompt-engineer instead."
---

# /prompt-craft — Skill & Prompt Engineering

When invoked standalone:
- If the user wants to create a new skill: start at **Create**
- If the user wants to fix a behavioral issue ("CC keeps doing X"): start at **Diagnose**
- If the user wants to improve an existing skill or prompt: start at **Audit**
- If the user wants to update the skill taxonomy: start at **Taxonomy**

When invoked from /coding-team Phase 2 as a design worker: the Team Leader provides scope. Focus your analysis on the prompt/skill dimensions of the task.

---

## Create — New Skill from Scratch

### 1. Clarify purpose

Before writing anything:
- What specific behavior should this skill produce?
- When should CC invoke it? (trigger phrases, task patterns)
- When should CC NOT invoke it? (false triggers to avoid)
- Is this a standalone skill or a pipeline phase?
- What's the context budget? (target line count)

### 2. Write frontmatter

The `description` field is the most important line in the skill. It controls when CC invokes it. Rules:
- Start with "Use when..." — CC pattern-matches on this
- Include trigger phrases the user would actually say
- Include negative triggers ("Do NOT use when...")
- Be specific. "Use for code tasks" triggers on everything. "Use when investigating a bug or test failure" triggers correctly.
- Keep it under 3 sentences

```yaml
---
name: skill-name
description: "Use when [specific trigger]. [What it does in one sentence]. [Do NOT use when / negative trigger]."
---
```

### 3. Write the body

Structure:
- **Identity preamble**: tell the agent what it IS ("You are the engineering manager", "You are implementing Task N"). Identity determines behavior more reliably than prohibitions — an engineering manager doesn't write code not because someone said "don't" but because it's not their job.
- **Standalone preamble** (if applicable): how to bootstrap when invoked directly vs from a pipeline
- **Core protocol**: the actual instructions, written as imperative commands
- **Decision points**: explicit if/then routing for any ambiguous situations
- **Red flags**: what CC should never do in this skill's context
- **Verification**: how to confirm the skill produced correct behavior

### 4. Language rules

Seven patterns that control CC behavior. Summary (read `skills/prompt-craft/language-rules.md` for full examples):

1. **Framing determines defaults** — desired path first, fallback second
2. **Name tools explicitly** — `Agent tool`, not "dispatch agents"
3. **Prohibitions must be explicit** — CC doesn't infer what not to do
4. **Identity over prohibition** — "you are the orchestrator" beats "NEVER write code." Use identity for foundational boundaries, prohibitions for operational rules.
5. **Name the rationalization** — when CC bypasses with "too simple" / "already handled" / "pre-existing", name the phrase and turn it into a compliance trigger
6. **Quantify thresholds** — "8+ files" not "large tasks"
7. **Tables beat prose for routing** — classification tables for any multi-path decision

### 5. Test the skill

After writing, evaluate with the audit checklist (see Audit section below).

---

## Diagnose — Why CC Isn't Following Instructions

When a user reports "CC keeps doing X instead of Y":

### Step 1: Identify the instruction

Find the exact line in the skill/prompt that should produce behavior Y. If it doesn't exist, the fix is adding it.

### Step 2: Check framing

Read the surrounding context. Common failure patterns:

| Symptom | Likely cause | Fix |
|---|---|---|
| CC uses the wrong tool | Desired tool isn't named explicitly, or the wrong tool is named first | Name the correct tool with exact syntax. Put it first in any conditional. |
| CC skips a step | Step is described as optional or implicit | Make it mandatory with explicit language ("MUST", "ALWAYS", "before proceeding") |
| CC does the opposite of what's written | Instruction is framed as an exception to the default | Flip the default. Make desired behavior the first/primary path. |
| CC half-follows instructions | Instructions are mixed with explanation | Separate imperative instructions from explanatory prose. Instructions first, rationale after. |
| CC follows the spirit but not the letter | Instructions use vague language | Replace "should", "consider", "try to" with "MUST", "DO", "ALWAYS" |
| CC only follows instructions early in conversation | Context window pressure pushes instructions out | Shorten the skill. Move details to on-demand files. Repeat critical rules at decision points. |
| CC defaults to subagents when you want agent teams | Subagent is framed as default, agent teams as exception | Flip the framing. Put agent teams path first. |
| CC writes code when it should delegate | No explicit prohibition on direct coding | Add "NEVER use Edit/Write directly. Spawn an agent." |
| CC constructs category exceptions ("just mechanical", "just test expectations") | Rule has no escape hatch but CC invents one | Name the specific rationalization as a compliance trigger (see Language Rules) |
| CC dismisses background task output without reading | No instruction to read output before acting on assumptions | Add "read output FIRST, then classify" — name "already handled" as rationalization |
| CC obeys reluctantly, finds new bypasses each session | Prohibition-based framing creates adversarial dynamic | Rewrite as identity framing — tell the agent what it IS, not what it can't do |

### Step 3: Check competing instructions

Search for contradictions:
- Does another skill or CLAUDE.md give conflicting guidance?
- Does the main SKILL.md say one thing but the phase file say another?
- Does a prompt template override the skill's instructions?

### Step 4: Propose fix

Write the minimal change. Prefer (in order):
1. **Name the rationalization** — if the agent bypasses with a specific phrase ("too simple", "already handled", "pre-existing"), name that phrase and turn it into a trigger. Cheapest, most targeted fix.
2. **Identity framing** — if the agent keeps fighting a boundary, rewrite as identity ("you are the orchestrator") instead of prohibition ("don't write code"). Fixes the root cause.
3. **Decision table** — if the agent doesn't know what to do, give it a classification table with signal keywords and actions. Replaces ambiguous prose.
4. **Explicit prohibition** — for specific operational rules where identity doesn't apply. Use sparingly — each prohibition is a future bypass opportunity.
5. **Reframing a conditional** — flip default/fallback ordering so the desired path comes first.
6. **Restructuring content** — most expensive. For context window pressure issues only.

### Step 5: Write a memory file

If this is a recurring issue, create a memory file in `memory/`:

```yaml
---
name: Short descriptive name
description: One-line summary of the behavioral issue
type: feedback
---

[What CC does wrong]

**Why:** [Root cause in the instructions]

**How to apply:** [The fix, stated as an instruction CC can follow]
```

### Step 6: Verify the fix held

In the next session where the behavior could recur, check:
- Did the agent follow the new instruction?
- Did it find a new bypass around it?
- If the fix held: update the memory file with "Verified: held in session on [date]"
- If the agent found a new bypass: escalate to the next fix tier (rationalization → identity → table → restructure)

---

## Audit — Evaluate an Existing Skill or Prompt

Read the skill/prompt file completely, then evaluate against this checklist:
For standard block templates, see `skills/prompt-craft/patterns-catalog.md`.

### Behavioral alignment

- [ ] Does the frontmatter `description` accurately describe when to trigger?
- [ ] Are there false-positive triggers? (would CC invoke this for tasks it shouldn't?)
- [ ] Are there false-negative triggers? (would CC miss tasks it should handle?)
- [ ] Is the desired default behavior stated first in every conditional?
- [ ] Are all tool names explicit? (no "dispatch agents" — specify which tool)
- [ ] Are prohibitions explicit? (not implied by the presence of a positive instruction)
- [ ] Are foundational boundaries framed as identity, not prohibition? ("you are X" not "don't do Y")
- [ ] Are known agent rationalizations named as compliance triggers?

### Context efficiency

- [ ] How many lines? Could any be moved to an on-demand file?
- [ ] Are there sections that only apply to rare situations? (move to conditional reads)
- [ ] Is there duplicated content that could be inlined as a 5-line summary instead?
- [ ] Would this skill still work if context was tight? (critical instructions near the top?)

### Clarity for CC

- [ ] Could CC follow every instruction without asking a question?
- [ ] Are thresholds quantified? (no "large", "complex", "many" without numbers)
- [ ] Do decision points have explicit routing? (tables or if/then, not "consider")
- [ ] Are examples provided for ambiguous patterns?
- [ ] Is rationale separated from instruction? (CC follows instructions, skims rationale)

### Standard blocks

- [ ] Does the file have enumerated-item-completion protection? (for any agent processing a list)
- [ ] Are replacement behaviors provided for every prohibition? ("NEVER X" must have "Instead, Y")
- [ ] Is the file under 200 lines? (context saturation threshold — see `patterns-catalog.md` tier table)
- [ ] Does the file have a "When You Cannot Complete" block? (for any agent that can get stuck)
- [ ] Is there a Finding Integrity block? (for any read-only auditor)
- [ ] Are escalation paths explicit? (BLOCKED, NEEDS_CONTEXT statuses defined)

### Prompt template quality (for `prompts/*.md`)

- [ ] Does the prompt tell the agent what it IS? ("You are implementing Task N")
- [ ] Does it tell the agent what it is NOT? (out-of-scope statement)
- [ ] Is full context provided? (agents don't inherit conversation history)
- [ ] Is the expected output format specified?
- [ ] Does it handle failure? (when to escalate, when to stop)
- [ ] Does it prevent common agent mistakes? (explicit prohibitions)

### Report format

```
AUDIT: [skill/prompt name]

PASS:
- [what's working well]

ISSUES:
- [severity] [issue]: [current text] → [suggested fix]
- [severity] [issue]: [current text] → [suggested fix]

CONTEXT:
- Current: N lines
- Recommended: N lines (move X to on-demand)
```

---

## Taxonomy — Skill Discovery Maintenance

The skill taxonomy (`~/.claude/skills/skill-taxonomy.yml`) maps skills to specialist worker roles so the Phase 2 Team Leader can pass relevant skills to each worker.

### Adding a skill

1. Determine which category the skill fits (debugging, verification, git-workflow, etc.)
2. If no category fits, create a new one with:
   - Category description
   - Role mappings (which specialist workers should see this skill)
3. Add the skill entry:

```yaml
category-name:
  skills:
    - name: skill-name
      path: skill-path
      description: "One-line description"
      use-when: "Trigger description"
  roles: [Senior Coder, Tester, ...]
```

### Removing a skill

Remove the entry. If the category is now empty, remove the category.

### Auditing the taxonomy

- Does every installed skill appear in the taxonomy?
- Are role mappings accurate? (would these workers actually benefit from this skill?)
- Are descriptions current? (skills evolve, taxonomy entries go stale)

---

## As a Phase 2 Design Worker

When the Team Leader spawns you as a specialist worker, your lens is:

**Focus:** Prompt quality, skill coverage, agent coordination patterns, instruction clarity.

**Questions to answer:**
- Are the existing agent prompts (`prompts/*.md`) well-suited for this task?
- Does this task need a new prompt template or modifications to an existing one?
- Will the skill advisory blocks the Team Leader passes to workers be useful or noise?
- Are there behavioral issues in the current skill/prompt setup that this task will hit?
- Does the task's coordination pattern (agent teams vs subagents) match its complexity signals?

**Output:** Findings, concerns, and recommendations from the prompt/skill lens. Flag any prompt templates that need updating before execution.
