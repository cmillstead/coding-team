---
name: second-opinion
description: "Use when you want an independent second opinion from a different AI model (OpenAI Codex CLI). Three modes: review (pass/fail gate on a plan or diff), challenge (adversarial — actively tries to break your code), and consult (open-ended question to a different model). Use after /review for cross-model coverage, or during Phase 4 planning for independent plan validation. Requires Codex CLI installed: npm install -g @openai/codex"
argument-hint: "[review|challenge|consult <question>] [model]"
---

Read and follow `~/.claude/skills/coding-team/skills/second-opinion/SKILL.md`, passing `$ARGUMENTS` through as the mode (`review`/`challenge`/`consult <question>`) and optional model.
