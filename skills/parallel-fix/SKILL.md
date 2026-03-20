---
name: parallel-fix
description: "Use when facing 3+ independent test failures or broken subsystems with different root causes. Dispatches one agent team per domain in parallel. Each team gets focused scope and constraints. Results are reviewed for conflicts and verified with a full test suite run."
---

# /parallel-fix — Parallel Agent Dispatch for Independent Failures

When invoked standalone:
- If the user provides failing tests or error output, group by independent domain
- If the user says "everything is broken" without specifics, run the test suite first to identify failures, then group
- After all teams return, run full test suite to verify (verification protocol)

When invoked from /coding-team, the lead provides grouped failures. Skip the above.

---

## When to Use

- 3+ test files failing with different root causes
- Multiple independent subsystems broken
- Each problem can be understood without context from others
- No shared state between investigations (not editing same files)

## When NOT to Use

- Failures are related (fix one might fix others)
- Need to understand full system state first
- Teams would interfere (editing same files, using same resources)
- Exploratory debugging (don't know what's broken yet)

## Choosing Coordination Mode

**Use native agent teams (when AGENT_TEAMS_AVAILABLE = true) if:**
- 3+ independent domains AND
- There is ANY chance domains share underlying infrastructure (shared DB, shared config, shared auth, shared state) AND
- Failures surfaced around the same time (possible common trigger)

**Use subagents (current behavior) if:**
- AGENT_TEAMS_AVAILABLE = false, OR
- Domains are provably independent (different repos, different services, zero shared code), OR
- 2 domains only (overhead not justified)

---

## The Pattern

### 1. Identify Independent Domains

Group failures by what's broken. Each domain must be independent — fixing one shouldn't affect another.

### 2. Assemble Investigation Teams

Each investigation team gets:
- **Specific scope** — one test file or subsystem
- **Clear goal** — make these tests pass / investigate this issue
- **Context** — paste error messages, test names, relevant code
- **Constraints** — don't change other code, don't edit files outside scope
- **Expected output** — summary of root cause and changes

Each team can be a single agent (for simple investigations) or a full task team (implementer + reviewers) for complex fixes.

### 3. Dispatch

**Agent teams mode (AGENT_TEAMS_AVAILABLE = true, 3+ domains, possibly shared infrastructure):**

1. Create team:
   `Teammate({ operation: "spawnTeam", team_name: "parallel-fix-<timestamp>" })`

2. Create tasks (one per domain):
   ```
   TaskCreate({
     subject: "Fix: <domain>",
     description: "<scope, goal, context, constraints, expected output>",
     activeForm: "Investigating <domain>..."
   })
   ```

3. Spawn one teammate per domain:
   - Spawn prompt includes: specific scope, error messages, relevant code, constraints, expected output format
   - Additional instruction: "If during investigation you discover this failure is related to another domain being investigated by a teammate, message them immediately. Do NOT proceed with a fix that depends on assumptions about another domain's state without coordinating."

4. Monitor:
   - Watch for cross-domain messages (the signal that "independent" failures may share a root cause)
   - If cross-domain dependency discovered: pause affected teams, re-scope, potentially merge into a single investigation
   - Otherwise: let teams work to completion

5. Review and integrate (same as subagent step 4 below)

6. Shutdown and cleanup:
   `Teammate({ operation: "requestShutdown", target_agent_id: "<each>" })`
   Wait for approvals.
   `Teammate({ operation: "cleanup" })`

**Subagent mode (AGENT_TEAMS_AVAILABLE = false, or 2 domains, or provably independent):**

Use the Agent tool with multiple calls in a single message. All teams run concurrently.

### 4. Review and Integrate

When teams return:
1. Read each summary — understand what changed
2. Check for conflicts — did teams edit same code?
3. Run full test suite — verify all fixes work together
4. Spot check — agents can make systematic errors

## Team Prompt Template

```
Fix the N failing tests in [file]:

1. "[test name]" - [error description]
2. "[test name]" - [error description]

Your task:
1. Read the test file and understand what each test verifies
2. Identify root cause
3. Fix the issue
4. Do NOT change code outside [scope]

Return: summary of root cause and what you fixed.
```

## Common Mistakes

- **Too broad** ("fix all the tests") — team gets lost. Be specific per domain.
- **No context** — paste error messages, don't just say "fix the race condition"
- **No constraints** — team might refactor everything outside their scope
- **Vague output** — "fix it" gives you no insight into what changed

## Verification Gate

Before claiming all fixes are complete:
1. IDENTIFY: What command proves this?
2. RUN: Execute full test suite fresh
3. READ: Full output, check exit code
4. VERIFY: Does output confirm all tests pass?
5. ONLY THEN: Make the claim
