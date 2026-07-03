## Agent Teams Lifecycle

All agent team usage follows this lifecycle. There is no `Teammate` tool — teams are formed implicitly by spawning agents that share a `team_name`, using the `Agent` tool.

```
1. CREATE TEAM
   Spawn the Team Leader via the Agent tool, passing `name` and `team_name`:
   Agent({ name: "<lead-name>", team_name: "<descriptive-name>", ... })
   - The team exists as soon as the first member is spawned with that team_name

2. CREATE TASKS
   TaskCreate({ subject, description, activeForm })
   - Set dependencies with blocked_by if tasks have ordering requirements

3. SPAWN TEAMMATES
   Use the Agent tool with the same `team_name` parameter to spawn each teammate
   - Each teammate gets: full context, clear scope, constraints, output format
   - Teammates auto-load CLAUDE.md, MCP servers, and skills
   - Teammates do NOT inherit lead's conversation history — include everything they need in the spawn prompt

4. COORDINATE
   - Monitor via TaskList for task status
   - Use SendMessage to check for and send messages to teammates
   - Broadcast (SendMessage to the team) when all teammates need the same information
   - Direct message (SendMessage to a named agent) for targeted coordination

5. SHUTDOWN
   For each teammate:
     TaskStop({ target_agent_id: "<id>" })
   Wait for each to confirm it has finished current work before stopping

6. CLEANUP
   - Only the lead performs cleanup
   - Verify all teammates are stopped before considering the team finished
   - The lead is responsible for reconciling shared team resources (task list, inbox state) before reporting completion
```

**Never:**
- Let teammates perform final cleanup (their team context may not resolve correctly)
- Skip shutdown and go straight to declaring the team done (check for active teammates first)
- Spawn teammates with a `team_name` before the lead itself has been spawned with that name
- Forget to include task-specific context in spawn prompts (teammates have no conversation history)
