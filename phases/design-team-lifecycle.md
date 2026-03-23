## Agent Teams Lifecycle

All agent team usage follows this lifecycle:

```
1. CREATE TEAM
   Teammate({ operation: "spawnTeam", team_name: "<descriptive-name>" })

2. CREATE TASKS
   TaskCreate({ subject, description, activeForm })
   - Set dependencies with blocked_by if tasks have ordering requirements

3. SPAWN TEAMMATES
   Use Task tool with team_name parameter to spawn into the team
   - Each teammate gets: full context, clear scope, constraints, output format
   - Teammates auto-load CLAUDE.md, MCP servers, and skills
   - Teammates do NOT inherit lead's conversation history — include everything they need in the spawn prompt

4. COORDINATE
   - Monitor via TaskList for task status
   - Check inbox for messages from teammates
   - Broadcast when all teammates need the same information
   - Direct message for targeted coordination

5. SHUTDOWN
   For each teammate:
     Teammate({ operation: "requestShutdown", target_agent_id: "<id>" })
   Wait for each to approve (they finish current work first)

6. CLEANUP
   Teammate({ operation: "cleanup" })
   - Only the lead runs cleanup
   - Verify all teammates are shut down before cleanup
   - Cleanup removes shared team resources (inbox, config, task files)
```

**Never:**
- Let teammates run cleanup (their team context may not resolve correctly)
- Skip shutdown and go straight to cleanup (check for active teammates first)
- Spawn teammates without the team existing (spawnTeam first)
- Forget to include task-specific context in spawn prompts (teammates have no conversation history)
