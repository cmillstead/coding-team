#!/bin/bash
# SessionStart hook: detects open PRs with failing CI checks and stale local branches.
# Warns the user about orphan PRs and stale branches before starting new work.
# All error paths exit 0 silently — only outputs JSON when issues found.

# Bail silently if gh or jq not available
command -v gh  >/dev/null 2>&1 || exit 0
command -v jq  >/dev/null 2>&1 || exit 0

# --- Orphan PR detection ---
# Fetch open PRs with status checks (10s timeout)
orphan_lines=""
pr_json=$(timeout 10 gh pr list --author @me --state open \
  --json number,title,statusCheckRollup --limit 20 2>/dev/null) || true

if [ -n "$pr_json" ] && echo "$pr_json" | jq empty 2>/dev/null; then
    # Build orphan report: for each PR, count checks with FAILURE conclusion
    orphan_lines=$(echo "$pr_json" | jq -r '
      [ .[] |
        { number, title,
          failing: [ .statusCheckRollup[]? |
                     select(.conclusion == "FAILURE" or .conclusion == "failure") ] |
          length } |
        select(.failing > 0) |
        "- #\(.number): \(.title) (\(.failing) failing check\(if .failing > 1 then "s" else "" end))"
      ] | .[]
    ' 2>/dev/null) || true
fi

# --- Stale branch detection ---
# Find local branches with no commits in the last 14 days and no open PR
stale_lines=""
cutoff=$(date -v-14d +%s 2>/dev/null || date -d '14 days ago' +%s 2>/dev/null) || cutoff=0

# Fetch all open PR head refs ONCE. Previously this hook made one `gh pr list
# --head` network call per stale branch, so session-start latency scaled with
# local branch count. One bounded call + local lookup keeps it constant-time.
open_pr_heads=$(timeout 10 gh pr list --state open --json headRefName --limit 200 2>/dev/null | jq -r '.[].headRefName' 2>/dev/null) || open_pr_heads=""

if [ "$cutoff" -gt 0 ]; then
    while IFS= read -r branch; do
        [ -z "$branch" ] && continue
        # Skip main/master/HEAD
        case "$branch" in
            main|master|HEAD|"* "*) continue ;;
        esac
        # Strip leading whitespace and asterisk
        branch=$(echo "$branch" | sed 's/^[* ]*//')
        [ -z "$branch" ] && continue

        # Get last commit timestamp
        last_commit=$(git log -1 --format=%ct "$branch" 2>/dev/null) || continue
        [ -z "$last_commit" ] && continue

        if [ "$last_commit" -lt "$cutoff" ]; then
            # Check if branch has an open PR (local lookup, no per-branch network call)
            if ! printf '%s\n' "$open_pr_heads" | grep -qxF "$branch"; then
                age_days=$(( ($(date +%s) - last_commit) / 86400 ))
                stale_lines="${stale_lines}- ${branch} (${age_days}d old, no PR)\n"
            fi
        fi
    done < <(git branch --format='%(refname:short)' 2>/dev/null)
fi

# --- Parked merged-branch detection ---
# Warn when the CURRENT branch of the repo (or a submodule) has already been
# merged upstream — i.e. the checkout is "parked" on dead work. Bounded to at
# most 2 gh lookups per run and skipped entirely if no timeout binary exists,
# so this never adds unbounded latency to session start.
parked_lines=""
TIMEOUT_CMD=$(command -v timeout || command -v gtimeout || true)
toplevel=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -n "$TIMEOUT_CMD" ] && [ -n "$toplevel" ]; then
    # Repo list: root first, then each .gitmodules path (in file order).
    parked_repo_paths="$toplevel"
    if [ -f "$toplevel/.gitmodules" ]; then
        sub_paths=$(git config --file "$toplevel/.gitmodules" --get-regexp '^submodule\..*\.path$' 2>/dev/null | sed -E 's/^[^ ]+ //') || sub_paths=""
        while IFS= read -r sub_path; do
            [ -z "$sub_path" ] && continue
            git -C "$toplevel/$sub_path" rev-parse --git-dir >/dev/null 2>&1 || continue
            parked_repo_paths="${parked_repo_paths}
${toplevel}/${sub_path}"
        done <<< "$sub_paths"
    fi

    parked_lookups=0
    while IFS= read -r repo; do
        [ -z "$repo" ] && continue
        [ "$parked_lookups" -ge 2 ] && break

        branch=$(git -C "$repo" branch --show-current 2>/dev/null)
        [ -z "$branch" ] && continue
        case "$branch" in
            main|master) continue ;;
        esac

        parked_lookups=$((parked_lookups + 1))
        merged_json=$( (cd "$repo" && "$TIMEOUT_CMD" -k 1 2 gh pr list --state merged --head "$branch" --json number,headRefOid --limit 10) 2>/dev/null ) || true
        [ -z "$merged_json" ] && continue
        echo "$merged_json" | jq empty 2>/dev/null || continue

        head_sha=$(git -C "$repo" rev-parse HEAD 2>/dev/null) || continue
        [ -z "$head_sha" ] && continue

        # Any entry whose headRefOid matches HEAD counts — a reused branch
        # name can have been merged more than once, and an older non-matching
        # entry must not shadow a later matching one.
        pr_number=$(echo "$merged_json" | jq -r --arg sha "$head_sha" \
          '[.[] | select(.headRefOid == $sha)] | .[0].number // empty' 2>/dev/null) || pr_number=""
        [ -z "$pr_number" ] && continue

        base=$(git -C "$repo" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
        if [ -z "$base" ]; then
            if git -C "$repo" show-ref --verify --quiet refs/heads/main 2>/dev/null; then
                base="main"
            elif git -C "$repo" show-ref --verify --quiet refs/heads/master 2>/dev/null; then
                base="master"
            else
                continue
            fi
        fi

        if [ "$repo" = "$toplevel" ]; then
            label="."
        else
            label="${repo#"$toplevel"/}"
        fi

        # Shell-escape the repo path and base branch for safe single-quoting
        # in the advertised recovery command — paths/branches may contain
        # spaces or shell metacharacters (e.g. a submodule path with a
        # space), and an unquoted embed would word-split or, worse, let a
        # crafted branch/path name execute unintended shell syntax if the
        # printed command is copy-pasted.
        q_repo=$(printf '%s' "$repo" | sed "s/'/'\\\\''/g")
        q_base=$(printf '%s' "$base" | sed "s/'/'\\\\''/g")

        parked_lines="${parked_lines}- ${label}: '${branch}' — PR #${pr_number} merged. Return: git -C '${q_repo}' checkout '${q_base}' && git -C '${q_repo}' pull --ff-only
"
    done <<< "$parked_repo_paths"
fi

# --- Build combined output ---
sections=""

if [ -n "$orphan_lines" ]; then
    orphan_reason=$(printf 'Open PRs with failing CI:\n%s\nAddress these first — fix CI failures or close with a reason. Starting new work while old PRs rot creates orphan debt.' "$orphan_lines")
    sections="$orphan_reason"
fi

if [ -n "$stale_lines" ]; then
    stale_reason=$(printf 'Stale local branches (>14d, no PR):\n%b\nConsider deleting with: git branch -d <name>' "$stale_lines")
    if [ -n "$sections" ]; then
        sections=$(printf '%s\n\n%s' "$sections" "$stale_reason")
    else
        sections="$stale_reason"
    fi
fi

if [ -n "$parked_lines" ]; then
    parked_reason=$(printf 'Checkout parked on a MERGED branch:\n%b' "$parked_lines")
    if [ -n "$sections" ]; then
        sections=$(printf '%s\n\n%s' "$sections" "$parked_reason")
    else
        sections="$parked_reason"
    fi
fi

if [ -n "$sections" ]; then
    jq -n --arg reason "$sections" '{"decision":"allow","reason":$reason}' || true
fi
