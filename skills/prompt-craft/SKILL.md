---
name: prompt-craft
description: "Use when writing, evaluating, or refining Claude Code skills or agent prompts. Covers: creating new SKILL.md files, auditing existing skills for behavioral issues, improving prompt templates for subagents/teammates, diagnosing why CC isn't following instructions, and maintaining the skill taxonomy. Also use as a Phase 2 design worker for tasks that involve prompt or skill changes."
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
- **Standalone preamble** (if applicable): how to bootstrap when invoked directly vs from a pipeline
- **Core protocol**: the actual instructions, written as imperative commands
- **Decision points**: explicit if/then routing for any ambiguous situations
- **Red flags**: what CC should never do in this skill's context
- **Verification**: how to confirm the skill produced correct behavior

### 4. Language rules

These patterns control CC behavior more than content does:

**Framing determines defaults.** Whatever comes first in a conditional is what CC will do. Put the desired path first, the fallback second.

```markdown
# BAD — CC will default to the simple path
If the task is complex, use agent teams.
Otherwise, use subagents.

# GOOD — CC will default to agent teams
Use agent teams for multi-agent coordination.
Fall back to subagents only if AGENT_TEAMS_AVAILABLE = false.
```

**Name the tools explicitly.** CC uses whatever tool name appears in the instructions. If you write "dispatch agents" CC picks whichever tool it's most familiar with. If you write `Teammate({ operation: "spawnTeam" })` CC uses that exact tool.

```markdown
# BAD — ambiguous
Dispatch workers to analyze the problem.

# GOOD — explicit
Spawn teammates via Teammate({ operation: "spawnTeam" }).
Create tasks via TaskCreate({ subject, description }).
```

**Prohibitions must be explicit.** CC doesn't infer what it shouldn't do. If you don't say "never write code directly in Phase 5" it will write code directly in Phase 5.

```markdown
# BAD — implies but doesn't prohibit
The main agent orchestrates and dispatches implementers.

# GOOD — explicit prohibition
The main agent orchestrates. It NEVER uses Edit, Write, or runs tests directly.
If you catch yourself writing code — STOP. Spawn an agent instead.
```

**Quantify thresholds.** "Large tasks" is ambiguous. "Tasks touching 8+ files" is mechanical.

**Tables beat prose for routing.** CC scans tables faster than paragraphs. Use tables for any decision with discrete inputs and outputs.

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

### Step 3: Check competing instructions

Search for contradictions:
- Does another skill or CLAUDE.md give conflicting guidance?
- Does the main SKILL.md say one thing but the phase file say another?
- Does a prompt template override the skill's instructions?

### Step 4: Propose fix

Write the minimal change. Prefer:
1. Adding an explicit prohibition (cheapest, most reliable)
2. Reframing a conditional (flip default/fallback ordering)
3. Adding a decision table (replaces ambiguous prose)
4. Restructuring content (more expensive, for context window issues)

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

---

## Audit — Evaluate an Existing Skill or Prompt

Read the skill/prompt file completely, then evaluate against this checklist:

### Behavioral alignment

- [ ] Does the frontmatter `description` accurately describe when to trigger?
- [ ] Are there false-positive triggers? (would CC invoke this for tasks it shouldn't?)
- [ ] Are there false-negative triggers? (would CC miss tasks it should handle?)
- [ ] Is the desired default behavior stated first in every conditional?
- [ ] Are all tool names explicit? (no "dispatch agents" — specify which tool)
- [ ] Are prohibitions explicit? (not implied by the presence of a positive instruction)

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
