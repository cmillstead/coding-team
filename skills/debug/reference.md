# Debug — Reference

## Phase 2: Pattern Analysis (detail)

Check if this bug matches a known pattern:

| Pattern | Signature | Where to look |
|---|---|---|
| Race condition | Intermittent, timing-dependent | Concurrent access to shared state |
| Nil/null propagation | TypeError, AttributeError | Missing guards on optional values |
| State corruption | Inconsistent data, partial updates | Transactions, callbacks, hooks |
| Integration failure | Timeout, unexpected response | External API calls, service boundaries |
| Configuration drift | Works locally, fails in CI/staging | Env vars, feature flags, DB state |
| Stale cache | Shows old data, fixes on cache clear | Redis, CDN, in-memory caches |

**Error research:** Use the `WebSearch` tool to search for exact error messages, stack traces, or unfamiliar error codes. Library documentation, GitHub issues, and Stack Overflow often have the root cause. Search BEFORE forming hypotheses — external knowledge prevents wasted investigation.

Also check:
- **Git log** for prior fixes in the same area — recurring bugs in the same files are an architectural smell, not coincidence
- Find working examples of similar code in the codebase and compare

## After 3+ Failed Fixes: Question Architecture (detail)

Pattern indicating an architectural problem:
- Each fix reveals new shared state/coupling in different places
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and escalate to user.** This is not a failed hypothesis — this is a wrong architecture.
