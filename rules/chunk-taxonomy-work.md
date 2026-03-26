---
globs:
  - "**/.claude/skills/**/*.md"
  - "**/SKILL.md"
  - "**/.claude/agents/**/*.md"
---

# Chunking Large Analysis Tasks
<!-- Deploy source: scripts/deploy.sh copies this to ~/.claude/rules/ -->

Large taxonomy, disambiguation, or classification tasks must be chunked to avoid context compaction mid-analysis:

- Break taxonomy work into clusters of 5-8 items per agent call — not 20+ items in one call
- Each chunk should be independently verifiable: include acceptance criteria per chunk
- Pass the full taxonomy as read-only reference but assign only 1 cluster for modification per agent
- After each chunk completes, verify results before dispatching the next chunk
- If an agent's output shows signs of context pressure (truncation, skipped items, reduced quality), reduce chunk size by 50%

Threshold: any analysis touching more than 10 items should be chunked. This applies to skill disambiguation, code audit findings, migration checklists, and similar batch work.
