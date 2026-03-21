---
name: Always use prompt-craft for skill/prompt changes
description: When a task involves writing or modifying skill instructions, agent prompts, or phase file content, use /prompt-craft audit before applying changes
type: feedback
---

Prompt-craft skill was created for exactly this scenario — writing instructions that control CC behavior. The planning worker skipped it when implementing phase reminders, treating the work as "mechanical markdown appends."

**Why:** Phase reminder content IS prompt engineering. The "Next Steps" sections are instructions CC follows. Prompt-craft audit caught 4 medium+ issues including emoji violations, unfollowable heuristics, promises of nonexistent behavior, and paraphrase risk.

**How to apply:** Any task that writes or modifies SKILL.md, phase files, prompt templates, or any markdown that CC reads as instructions must go through /prompt-craft audit before being applied. Route through Phase 2 with Prompt/Skill Specialist if starting from scratch, or run /prompt-craft audit on proposed content before execution.
