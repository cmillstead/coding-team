---
name: Dispatch first, self-execute second
description: Orchestrator must dispatch agent work before doing its own lightweight tasks to maximize parallelism
type: feedback
---

Dispatch delegatable work (agent tasks) BEFORE doing self-executable work (memory saves, doc writes, context reads).

**Why:** Agent observed doing its own memory-save task first, then dispatching an agent for 3 code tasks. This serialized work that could have overlapped — the code agents could have been running while the orchestrator saved memory.

**How to apply:** At any point where the orchestrator has a mix of tasks — some for agents, some for itself — dispatch ALL agent work first, then do lightweight self-tasks while agents run. Agent work takes longer; starting it immediately maximizes parallelism.
