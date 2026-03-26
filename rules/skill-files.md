---
globs:
  - "**/.claude/skills/**/*.md"
  - "**/.claude/skills/**/SKILL.md"
  - "**/.claude/skills/**/phases/**"
  - "**/SKILL.md"
---

# Skill & CC Instruction File Rules

- Keep skill instructions under 200 lines — context saturation degrades compliance beyond this
- Use identity framing ("You are the orchestrator") over prohibition ("NEVER write code directly")
- Include verification steps in every phase
- Cross-reference related skills to prevent routing collisions
- Name known rationalizations as compliance triggers — do not rely on prohibition alone
- Name tools explicitly: "Agent tool", "Edit tool", "Bash tool" — not "dispatch agents" or "use tools"
- Quantify thresholds: "3 files", "5 minutes", "2 rounds" — not "large", "many", "several"
- Lead with identity framing in the first line: "You are the [role]" — this sets behavioral defaults stronger than any prohibition
- Name the top 3 rationalizations agents use to skip the rule, and add them as explicit compliance triggers:
  - "Only warnings, not errors" — warnings ARE errors for quality gates
  - "I'll do it myself since it's small" — size does not exempt delegation rules
  - "The tool isn't available" — verify availability before assuming; use fallback patterns
- When a prohibition is necessary, pair it with the named rationalization: "NEVER skip tests. Known rationalization: 'only warnings, no errors' — this does not apply"
