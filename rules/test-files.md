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

- Use real implementations, NEVER mocks — only mock external paid APIs with no test mode
- Every test must assert something — no empty test bodies or `pass` placeholders
- Follow AAA pattern: Arrange, Act, Assert — clearly separated sections
- Prefer `pytest` fixtures over setup/teardown methods
- NEVER disable or skip tests to make CI pass
- NEVER use `@pytest.mark.skip` without a linked issue explaining when it will be unskipped
- Test names must describe the behavior being verified, not the method name
