---
globs:
  - "**/.claude/skills/**/*.md"
  - "**/SKILL.md"
  - "**/.claude/agents/**/*.md"
---

# Pre-computation Rule for Orchestrators

Before dispatching worker agents, pre-compute external data they will need:

- Run dependency audits (`npm audit`, `pip audit`, `cargo audit`) at orchestrator level and pass results as data to workers
- Fetch CVE databases or security advisories before dispatching security review workers
- Run secret scanning tools before dispatching code review workers
- Gather test coverage reports before dispatching test improvement workers
- Read configuration files before dispatching workers that need config context

Workers under context pressure skip external tool calls. The orchestrator has more budget — do the I/O upfront and pass structured data to workers via their prompt.
