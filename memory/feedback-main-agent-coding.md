---
name: Main agent writes code instead of delegating
description: During Phase 5 execution, the main agent uses Edit/Write directly instead of dispatching implementer subagents
type: feedback
---

The main agent does the coding itself during Phase 5 instead of dispatching implementer subagents via the Agent tool. User sees code diffs on screen from the main agent.

**Why:** The execution phase instructions said "dispatch implementer" but never explicitly prohibited the main agent from writing code. LLMs interpret task details as instructions to do the work directly.

**How to apply:** Phase 5 must have an explicit prohibition: the main agent orchestrates (dispatch, read results, decide next steps) but never uses Edit, Write, or runs tests directly. Only Agent tool calls for code changes during execution.
