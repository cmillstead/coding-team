---
name: Main agent writes code instead of delegating
description: During Phase 5 execution, the main agent uses Edit/Write directly instead of dispatching implementer subagents
type: feedback
---

The main agent does the coding itself during Phase 5 instead of spawning implementer teammates. User sees code diffs on screen from the main agent.

**Why:** The execution phase instructions said "dispatch implementer" but never explicitly prohibited the main agent from writing code. LLMs interpret task details as instructions to do the work directly.

**How to apply:** Phase 5 has an allowed-tools whitelist in the CRITICAL block: Agent, Teammate, SendMessage, TaskCreate/TaskList/TaskUpdate, Read, and git-only Bash. Any Edit/Write/test-Bash usage means the task must be re-done by an agent — direct edits bypass the audit loop and are not trusted. The mid-phase reminder (every 3 tasks) re-asserts the orchestrator role.
