---
globs:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.tsx"
  - "**/*.jsx"
---

# Dark Feature Detection

When reviewing or auditing code, check for implemented-but-unwired features:

- After implementing a feature, verify it is reachable from at least 1 entry point (route, CLI command, event handler, or test)
- Search for exported functions/classes that have 0 callers outside their own module — these may be dark features
- Check that new routes/endpoints are registered in the router, not just defined
- Verify event handlers are subscribed, not just declared
- If a feature exists in code but has no path to execution, flag it explicitly: "DARK FEATURE: {name} is implemented but not wired to any entry point"
