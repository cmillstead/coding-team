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

**Replacement behaviors must accompany prohibitions.** Every "NEVER do X" must include "Instead, do Y." A prohibition without a replacement behavior creates either paralysis (agent doesn't know what to do) or agent-invented workarounds (which may be worse than the original behavior).

```markdown
# BAD — prohibition with no alternative
NEVER suggest fixing only a subset of findings.

# GOOD — prohibition with explicit replacement
NEVER suggest fixing only a subset of findings. Instead, present all
findings in priority-ordered batches: Batch 1 (P1s), Batch 2 (P2s),
Batch 3 (P3s).
```

**Position determines survival under pressure.** Critical instructions placed near the top of a file survive context pressure. Instructions past line 200 are the first to degrade. The MANDATORY block in ct-implementer.md works because it's at the top — the Enumerated Item Completion section at line 201 is at risk.

Guideline: Front-load the 3-5 most critical rules in any agent prompt. If a rule is important enough to name, it's important enough to place in the top 100 lines.

**Standard blocks for standard problems.** Reusable template blocks (Finding Integrity, MCP Resilience, Enumerated Completion) are more reliable than ad-hoc instructions. They're battle-tested across 12 audit cycles and consistent across agents. When a known pattern applies, use the standard block from `patterns-catalog.md` rather than writing a one-off instruction.

```markdown
# BAD — ad-hoc instruction for a solved problem
Make sure to report all findings, even pre-existing ones.

# GOOD — use the battle-tested standard block
Use the Finding Integrity block verbatim from patterns-catalog.md.
```
