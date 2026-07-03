---
name: Hook consolidation round 2
description: Second consolidation — killed 4 hooks (23→19), merged metrics-analyzer and symlink-integrity into hook-health-check
type: project
---

Second hook consolidation round. First round (cycle 9) went 28→16. Hook count crept back to 23 over cycles 10-14 due to harness-engineer adding 1-2 hooks per audit cycle.

**Actions taken:**
- Killed `test-gap-correction.py` — coverage at 243, no longer needed
- Killed `track-artifacts-in-repo.py` — git workflow catches untracked files
- Killed `symlink-integrity-check.py` — merged core check into hook-health-check.py
- Merged `metrics-analyzer.py` into `hook-health-check.py` (both SessionStart)
- Migrated `hook-health-check.py` to use `_lib/output.allow_with_reason()`
- `feedback-promotion-checker.py` left as-is — standalone CLI tool, not a hook consumer

**Result:** 23→19 hooks, 243→205 tests, all passing. PR #38.

**Why:** Hook accumulation pattern identified — harness-engineer recommends hooks without cost/benefit analysis. New feedback memory created to prevent recurrence.

**How to apply:** When next audit cycle recommends new hooks, check hook count first. If >20, consolidate before adding. Prefer merging into existing hooks over creating new ones.
