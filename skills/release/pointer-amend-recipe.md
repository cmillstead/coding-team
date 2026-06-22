# Pointer-Amend Recipe (Two-Repo Submodule Flow)

Use this when a change spans both the coding-team submodule AND the root repo. The root repo holds a submodule pointer; if you push root before the submodule PR merges, the pointer records a pre-merge commit. This recipe eliminates that lag.

## The Problem

PR #82 had a benign one-commit pointer lag: root was pushed before the submodule merge finalized, so the root pointer pointed to the branch tip rather than the merged main tip. PR #19 fixed this by amending the root pointer to the merged submodule tip before pushing root.

## The Recipe

1. **Merge the submodule PR first.**
   ```bash
   gh pr merge <sub-PR-number> --merge --delete-branch
   ```
   (GitHub UI is an alternative, but `gh pr merge` is canonical here.)
   GATE: do not stage, amend, or push the root repo until the submodule PR shows MERGED:
   ```bash
   gh pr view <sub-PR-number> --json state -q .state   # must return "MERGED"
   ```

2. **Pull the merged submodule tip.**
   ```bash
   git -C skills/coding-team checkout main
   git -C skills/coding-team pull
   ```

Run steps 3–5 from the ROOT repo working directory (not from within skills/coding-team).

3. **Stage the updated submodule pointer in the root repo.**
   ```bash
   git add skills/coding-team
   ```

4. **Amend the root commit to record the TRUE merged tip.**
   If the root pointer commit has not yet been pushed:
   ```bash
   git commit --amend --no-edit
   ```
   If the root commit was already pushed (rare; requires force-push approval):
   create a new commit instead:
   ```bash
   git commit -m "fix: update submodule pointer to merged tip"
   ```

5. **Push the root repo.**
   ```bash
   git push -u origin HEAD
   ```
   The root PR now records the merged submodule tip — no pointer lag.

6. **Verify the pointer is correct.**
   ```bash
   git submodule status
   ```
   Confirm the recorded tip (the SHA shown) equals the merged submodule tip (`gh pr view <sub-PR-number> --json mergeCommit -q .mergeCommit.oid`). A leading `+` in the output means the working-tree submodule has diverged from the recorded pointer — recheck steps 2–5.

## When This Applies

- The feature branch in the root repo contains a submodule pointer bump to a branch commit.
- The submodule PR merges to `main` before (or at the same time as) the root PR.
- You want the root PR's recorded pointer to be the final merged commit, not the pre-merge branch tip.

If the root and submodule land simultaneously or independently (no cross-dependency), run step 6 anyway to confirm no pointer drift.
