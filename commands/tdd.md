---
name: tdd
description: Implement a feature or fix using red-green-refactor TDD cycle
---

# /tdd — Test-Driven Development

## The Cycle

1. **RED** — write one failing test showing desired behavior
2. **Verify RED** — run test, confirm it fails for the right reason (feature missing, not typo)
3. **GREEN** — write minimal code to pass the test
4. **Verify GREEN** — run test, confirm it passes, no other tests broken
5. **REFACTOR** — clean up, keep tests green
6. **Repeat**

## Rules

- If code is written before a test: delete it, start over with the test. No exceptions without user permission.
- Never mock what you can use for real — only mock external systems genuinely unavailable in the test environment.
- Never mock the thing being tested.
- Every implementation batch ends with: run tests -> run linter -> confirm both pass -> commit.

## Verification Gate

Before claiming any step is complete:
1. IDENTIFY: What command proves this?
2. RUN: Execute it fresh
3. READ: Full output, check exit code
4. VERIFY: Does output confirm the claim?
5. ONLY THEN: Make the claim
