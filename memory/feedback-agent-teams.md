---
name: Agent teams as default, not subagents
description: Use agent teams (Teammate + SendMessage) as the primary coordination mechanism, not subagents. Subagents are fallback only.
type: feedback
---

When AGENT_TEAMS_AVAILABLE = true, agent teams are the default for ALL multi-agent coordination. Do not use subagents when agent teams are available.

**Why:** The skill previously framed agent teams as "the exception" with subagents as default. CC read this literally and almost always used subagents, ignoring agent teams instructions. The "default is subagents" language, subagent-first routing tables, and narrow agent-teams triggers all reinforced the wrong behavior.

**How to apply:** Agent teams path comes first in all phase files and standalone skills. Subagent path is labeled "fallback" and only used when AGENT_TEAMS_AVAILABLE = false or for genuinely single-agent tasks (one reviewer, one planning worker). Never write "default is subagents" or routing tables with mostly "No" for agent teams.
