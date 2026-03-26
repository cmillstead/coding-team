---
globs:
  - "**/*.json"
  - "**/*.yml"
  - "**/*.yaml"
  - "**/*.toml"
  - "**/.*rc"
  - "**/.env.example"
---

# Config File Rules
<!-- Deploy source: scripts/deploy.sh copies this to ~/.claude/rules/ -->

- NEVER commit secrets, tokens, API keys, or credentials
- Validate JSON/YAML/TOML syntax before saving
- Use comments (where format supports them) to explain non-obvious values
- Keep config files sorted alphabetically where order does not matter
- NEVER modify production config without explicit user confirmation
