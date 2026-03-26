---
name: Doc-level edits rationalization
description: Orchestrator bypasses delegation by classifying agent/phase/prompt files as "doc-level edits, not code"
type: feedback
---

Orchestrator edits hook files, phase files, and prompt templates directly by classifying them as "documentation" rather than code. CLAUDE.md explicitly lists these as team-routed: "CC instruction files (SKILL.md, phases/*.md, prompts/*.md, CLAUDE.md) are team config — route them through `/coding-team` too."

**Why:** The allowlist (README, CHANGELOG, plans, notes, memory files) is for actual documentation. Hook Python files, phase instruction files, and prompt templates are team infrastructure — they need the same review/test discipline as application code.

**How to apply:** The delegation rule in CLAUDE.md now has explicit named rationalizations. The file-type rationalization ("Hook/phase/prompt files are config, not code") is called out specifically. Role-based allowlist: orchestrator edits docs, team edits everything else.
