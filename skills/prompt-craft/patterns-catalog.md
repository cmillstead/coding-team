# Prompt-Craft Patterns Catalog

Reference of battle-tested patterns for agent prompts. Use when writing or auditing agent definitions (`agents/*.md`), phase files (`phases/*.md`), and skills (`skills/*/SKILL.md`).

---

## 1. Enumerated Item Completion

**When:** Any agent processes a list of items (findings, files to modify, hooks to migrate, tests to write).

**Problem:** Agents process ~50% of enumerated items then report DONE. Named rationalizations: "The pattern is established, remaining items follow the same approach" and "I've done the representative ones."

**Template:**
```
You must process ALL N items listed below. After completion, report:
- Items assigned: N
- Items completed: [count]
- Items skipped: [count with reason for each]

The orchestrator will verify your count matches the assignment.
Known rationalization: "The pattern is established" — every item must be individually processed.
```

**Example:** `agents/ct-implementer.md` lines 201-213.

---

## 2. Replacement Behavior Pairing

**When:** Writing a prohibition (NEVER, DO NOT, MUST NOT).

**Problem:** A prohibition without a replacement behavior causes either paralysis (agent doesn't know what to do instead) or agent-invented workarounds (which may be worse).

**Template:**
```
NEVER [prohibited action]. Instead, [replacement behavior].
```

**Example:** In `agents/ct-harness-engineer.md`, the completionist identity says "NEVER end with 'Want me to route [subset]?'" and provides the batch action template as the replacement.

---

## 3. Finding Integrity Block

**When:** Any read-only auditor agent (spec reviewer, simplify auditor, harden auditor, QA reviewer).

**Problem:** Auditors dismiss findings with "pre-existing" or "not a regression" — both are rationalizations.

**Template:**
```
## Finding Integrity

"Pre-existing" and "not a regression" are NOT valid reasons to skip a finding.
If the code has a defect — regardless of when it was introduced — report it.
Known rationalization: "this was already there before the changes" — it's still a finding.
```

**Example:** `agents/ct-spec-reviewer.md` lines 155-159.

---

## 4. MCP Resilience Block

**When:** Any agent with MCP tools (codesight-mcp, QMD, context-keep).

**Problem:** Agents retry failed MCP tools indefinitely, crashing sessions.

**Template:**
```
If ANY [mcp-server-name] tool call returns a connection error, timeout, or API error:
do NOT retry it. Mark the tool unavailable for this session and fall back to
[fallback tools]. Known rationalization: "maybe it's back up now" — it isn't.
One retry is the maximum.
```

**Example:** `agents/ct-harness-engineer.md` lines 88-97.

---

## 5. Completionist Identity

**When:** Any agent that processes a list of findings, scan results, or audit items.

**Problem:** Agents suggest fixing only critical items, silently dropping lower-severity work.

**Template:**
```
You are a completionist [role]. Your default is ALL findings, ALL severities.

Severity determines execution ORDER (P1 first), not scope (P1 only).

**Named rationalizations:**
- "Let's start with the P1s" → Plan for all, execute in priority order.
- "The P3s can wait for the next cycle" → They won't. Fix them now.
- "Focus on the critical ones first" → Severity = order, not scope.

**Only the user can reduce scope.**
```

**Example:** `agents/ct-harness-engineer.md` lines 52-65.

---

## 6. Cross-Agent Propagation Checklist

**When:** After writing or modifying any agent prompt.

**Problem:** A fix in one agent doesn't propagate to siblings that face the same failure class (Case 16).

**Template:**
After modifying an agent prompt, check:
1. Does any sibling agent (`agents/*.md`) face the same failure class?
2. If yes, does that sibling have equivalent protection?
3. Key patterns to propagate: MCP resilience, finding integrity, enumerated completion, identity-negative.

**Example:** Case 16 — fix in ct-implementer.md for "pre-existing" dismissal had to propagate to all auditors.

---

## 7. Context Pressure Degradation Tiers

**When:** Deciding how long a file can be, or where to place critical instructions.

**Problem:** Beyond ~200 lines of agent context, MANDATORY labels stop working reliably.

**Tiers:**
| Lines | Effect | Mitigation |
|-------|--------|------------|
| < 100 | Full compliance | None needed |
| 100-200 | Reliable | Front-load critical rules |
| 200-300 | Degradation begins | Extract to on-demand files, keep core under 200 |
| 300-400 | MANDATORY labels unreliable | Required output fields, orchestrator checkpoints |
| 400+ | Severe degradation | Restructure into smaller files |

**Example:** `agents/ct-implementer.md` at 237 lines — MANDATORY block at top survives, Enumerated Completion at line 201 is at risk.

---

## 8. Structural Demotion Detection

**When:** Auditing an agent prompt or skill file.

**Problem:** Items placed in separate "Additional" or "Advisory" sections are treated as optional under context pressure (Case 9).

**Detection:** Look for:
- Sections named "Additional", "Optional", "Advisory", "Nice to Have"
- Items placed after the main protocol, separated by a heading
- Tool lists split between "Primary" and "Secondary"

**Fix:** Colocate all mandatory items in the same block. Separation = demotion.

**Example:** Case 9 — tools in a separate "Additional Tools" section were never used.

---

## 9. Identity-Negative Pattern

**When:** Writing the identity preamble for any agent.

**Problem:** "You are X" sets the role but doesn't exclude adjacent roles the agent might drift into.

**Template:**
```
You are the [role] on the coding team. You [primary responsibility].

You are NOT a [adjacent role 1]. Do not [what that role does].
You are NOT a [adjacent role 2]. [What that role handles] is out of scope.
```

**Example:** `agents/ct-harness-engineer.md` lines 24-37:
- "You are the harness engineer..."
- "You are NOT a prompt-craft auditor..."
- "You are NOT an implementer..."
