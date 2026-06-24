---
globs:
  - "**/test_*.py"
  - "**/*_test.py"
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - "**/*.test.js"
  - "**/*.spec.js"
  - "**/tests/**"
---

# Test File Rules
<!-- Deploy source: scripts/deploy.sh copies this to ~/.claude/rules/ -->

- Use real implementations, NEVER mocks — only mock when a dependency is physically impossible to run locally: external paid API with no test mode (e.g. Stripe, Bittensor), hardware not available in CI (e.g. GPU), or a local LLM / Ollama model not installed locally
- Every test must assert something — no empty test bodies or `pass` placeholders
- Follow AAA pattern: Arrange, Act, Assert — clearly separated sections
- Prefer `pytest` fixtures over setup/teardown methods
- NEVER disable or skip tests to make CI pass
- NEVER use `@pytest.mark.skip` without a linked issue explaining when it will be unskipped
- Test names must describe the behavior being verified, not the method name
