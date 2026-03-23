# Prompt Language Rules

> Loaded from `skills/prompt-craft/SKILL.md` Step 4. Return to SKILL.md after reading.

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

**Identity over prohibition.** Telling the agent *who it is* changes *what it wants to do*. "You are the engineering manager" produces better delegation than "NEVER write code directly." Prohibitions create an adversarial frame the agent optimizes around; identity creates intrinsic behavior. Use identity for foundational boundaries (who does what), prohibitions for specific operational rules.

```markdown
# BAD — prohibition (agent treats as constraint to optimize around)
You MUST NOT write code during Phase 5. NEVER use Edit or Write.

# GOOD — identity (agent treats as self-description)
You are the orchestrator. Your job is coordination, not implementation.
Your team writes code. You dispatch them via Agent tool.
```

**Name the rationalization.** When CC bypasses a rule, it constructs a reason: "this is too simple," "already handled," "just test expectations," "only warnings." Name the specific bypass phrase and turn it into a compliance trigger. This intercepts the reasoning chain, not just the action.

```markdown
# BAD — prohibition that CC will find exceptions to
Always use /coding-team for code changes. No exceptions.

# GOOD — names the bypass and turns it into a trigger
The thought "this is too simple for /coding-team" is itself the signal
to use /coding-team. If you're constructing a reason why an edit
"doesn't count," that reasoning is the bypass.
```

**Quantify thresholds.** "Large tasks" is ambiguous. "Tasks touching 8+ files" is mechanical.

**Tables beat prose for routing.** CC scans tables faster than paragraphs. Use tables for any decision with discrete inputs and outputs. When the agent doesn't know what to do (CI failures, error classification, model selection), a classification table with signal keywords and actions is often the right first answer.
