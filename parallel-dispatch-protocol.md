# Parallel Dispatch Protocol

When and how to dispatch multiple agent teams in parallel for independent problems.

## When to Use

- 3+ test files failing with different root causes
- Multiple independent subsystems broken
- Each problem can be understood without context from others
- No shared state between investigations (not editing same files)

## When NOT to Use

- Failures are related (fix one might fix others)
- Need to understand full system state first
- Teams would interfere (editing same files, using same resources)
- Exploratory debugging (don't know what's broken yet)

## The Pattern

### 1. Identify Independent Domains

Group failures by what's broken. Each domain must be independent — fixing one shouldn't affect another.

### 2. Assemble Investigation Teams

Each investigation team gets:
- **Specific scope** — one test file or subsystem
- **Clear goal** — make these tests pass / investigate this issue
- **Context** — paste error messages, test names, relevant code
- **Constraints** — don't change other code, don't edit files outside scope
- **Expected output** — summary of root cause and changes

Each team can be a single agent (for simple investigations) or a full task team (implementer + reviewers) for complex fixes.

### 3. Dispatch in Parallel

Use the Agent tool with multiple calls in a single message. All teams run concurrently.

### 4. Review and Integrate

When teams return:
1. Read each summary — understand what changed
2. Check for conflicts — did teams edit same code?
3. Run full test suite — verify all fixes work together
4. Spot check — agents can make systematic errors

## Team Prompt Template

```
Fix the N failing tests in [file]:

1. "[test name]" - [error description]
2. "[test name]" - [error description]

Your task:
1. Read the test file and understand what each test verifies
2. Identify root cause
3. Fix the issue
4. Do NOT change code outside [scope]

Return: summary of root cause and what you fixed.
```

## Common Mistakes

- **Too broad** ("fix all the tests") — team gets lost. Be specific per domain.
- **No context** — paste error messages, don't just say "fix the race condition"
- **No constraints** — team might refactor everything outside their scope
- **Vague output** — "fix it" gives you no insight into what changed
