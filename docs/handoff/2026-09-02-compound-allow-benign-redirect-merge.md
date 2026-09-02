# Handoff — Merge `harness/compound-allow-benign-redirect` into main

**Tracker:** TRK-212
**Date:** 2026-09-02
**Repo:** coding-team (`~/.claude/skills/coding-team`)
**Status:** RESOLVED — all 6 commits superseded on main; nothing to merge (investigation 2026-09-02)

## Resolution (2026-09-02)

Investigated before merging (verify-before-reapply). Every commit is already on
main or built on a surface main deliberately removed. Nothing to route to
coding-team; no code change to main. Per-commit drop reasons:

- `c0ceb13` nvm gate — **already on main, byte-identical** (`_is_nvm_bootstrap`, `_NVM_SOURCE_RE`, `_NVM_CMD_RE`, the block at guard section 0). Main got it independently.
- `2995c21` nvm fail-open + honest message — **already on main** (main's `_is_nvm_bootstrap` has the `except: return False` fail-open + the same redirect-to-absolute-path message).
- `a32e206` auto-allow read-only loops — **superseded/rejected.** Main commit `dd85530` (2026-06-24) deleted the ENTIRE auto-allow surface (`should_auto_allow`, `decompose_atoms`, settings machinery) after multiple Codex rounds, calling it "the C10 command-grammar arms-race source." Re-adding = reverting a newer cross-model-reviewed security decision.
- `68f7dfe` tolerate benign redirects — **moot.** Main's `is_multi_statement` already never false-denies redirects (`2>&1`, `>&2`, `&>file`, `2>&-`, `<&3`, `1>&2` all return False; 16 tests). No auto-allow surface left to protect.
- `27b85d2` tighten benign-redirect strip — **moot.** Fix to auto-allow code main deleted.
- `f713ae7` fd-dup terminator on redirect strip — **moot.** Fix to auto-allow code main deleted.

Evidence: `hooks/tests/test_compound_allow.py` + `hooks/tests/test_git_safety_guard.py` = 247 passed on main HEAD. Main compound_allow docstring: "there is NO auto-allow surface anymore."

Remaining action: delete stale branch `harness/compound-allow-benign-redirect` (requires `-D`, commits unmerged & staying that way), close TRK-212.

---
### Original handoff (below) — task as it was scoped before investigation

**Status:** not started — real unmerged work, blocked on 2+ months of drift/conflicts

## Task

An abandoned local branch, `harness/compound-allow-benign-redirect`, holds 6 commits of genuine fixes to the git-safety guard and its compound-command auto-allow helper. It never had a PR, drifted 2+ months from `main`, and now conflicts. Bring its intent onto `main` cleanly.

## The 6 commits (oldest → newest)

- `c0ceb13` feat: nvm-bootstrap deny gate + regression tests
- `2995c21` fix: nvm gate fail-open + honest message + non-vacuous allow-tests (2a)
- `a32e206` feat: auto-allow read-only loop compounds in compound_allow (fail-safe)
- `68f7dfe` feat: tolerate benign /dev/null & fd-dup redirects in compound auto-allow
- `27b85d2` fix: tighten benign-redirect strip to /dev/null-exact + std-stream fds (cross-model review)
- `f713ae7` fix: require complete-word terminator on fd-dup redirect strip (cross-model review)

Net intent: (1) a deny gate for nvm-bootstrap commands (fail-open, honest message), and (2) widen `compound_allow` to auto-allow read-only loop compounds and tolerate *benign* redirects (`/dev/null`-exact, std-stream fd-dups), with two later tightening fixes from a prior cross-model review.

## Conflicts (merge-tree vs `origin/main`, all content conflicts)

- `config/command-hygiene.md`
- `hooks/_lib/compound_allow.py`
- `hooks/git-safety-guard.py`   ← most sensitive; the trust boundary
- `hooks/tests/test_compound_allow.py`
- `hooks/tests/test_git_safety_guard.py`

The branch and `main` both evolved these files independently. `main` has had multiple git-safety-guard changes since the branch diverged — some of the branch's fixes may already exist on main in a different form; verify before re-applying (avoid double-applying or reverting a newer main fix).

## Approach

Route through `/coding-team` (this is trust-boundary code — do NOT hand-merge on main; main commits are hook-blocked anyway):

1. Branch fresh from `origin/main` (per house rule).
2. Replay the 6 commits (cherry-pick or interactive rebase), resolving conflicts one file at a time. For each conflict, first `git log origin/main -- <file>` to learn what main changed, then reconcile — keep main's newer guard behavior, layer the branch's intent on top; never weaken an existing guard to resolve a conflict.
3. For each of the 6 commits' features, check whether main already has an equivalent (some may be superseded); drop what's redundant, keep what's genuinely new.
4. Full hook test suite green from repo root: `python3 -m pytest -q` (name the scope in the green claim).
5. Cross-model review (`/second-opinion` Codex) on the whole diff — mandatory: git-safety-guard is a trust boundary, and the branch's own history shows a prior cross-model round already caught redirect-strip bugs (`27b85d2`, `f713ae7`) — same class of edge case to watch.
6. PR + merge; then delete the old `harness/compound-allow-benign-redirect` branch.

## Acceptance criteria

- The nvm-bootstrap deny gate and the compound_allow benign-redirect / read-only-loop widening are on `main`, or explicitly dropped-as-superseded with a one-line reason per dropped commit.
- Full hook suite green; no existing guard behavior weakened (regression tests for the old behavior pass).
- Cross-model reviewed; findings fixed.
- Old branch deleted after merge.

## Risks / landmines

- `hooks/git-safety-guard.py` is the most load-bearing guard in the harness; a careless conflict resolution can silently weaken it. Resolve conservatively and lean on the regression tests + Codex.
- Benign-redirect stripping is edge-case-heavy (the branch's last 2 commits are exactly such fixes). Re-derive the redirect-strip logic against current main rather than blindly taking either side.

## Context

Surfaced while cleaning up stale local branches after shipping the clean-tree completion guard (PR #159, merged 2026-09-02). Its sibling stale branch `wip/ci-watch` was deleted the same day (superseded by shipped ci-watch PR #155). This branch was NOT deleted because its 6 commits are real, unmerged work.
