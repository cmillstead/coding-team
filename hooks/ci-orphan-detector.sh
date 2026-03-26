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
            # Check if branch has an open PR
            has_pr=$(timeout 5 gh pr list --head "$branch" --state open --json number --limit 1 2>/dev/null)
            if [ -z "$has_pr" ] || [ "$has_pr" = "[]" ]; then
                age_days=$(( ($(date +%s) - last_commit) / 86400 ))
                stale_lines="${stale_lines}- ${branch} (${age_days}d old, no PR)\n"
            fi
        fi
    done < <(git branch --format='%(refname:short)' 2>/dev/null)
fi

# --- Build combined output ---
reason=""
stale_reason=""

if [ -n "$orphan_lines" ]; then
    reason=$(printf 'Open PRs with failing CI:\n%s\nAddress these first — fix CI failures or close with a reason. Starting new work while old PRs rot creates orphan debt.' "$orphan_lines")
fi

if [ -n "$stale_lines" ]; then
    stale_count=$(printf '%b' "$stale_lines" | grep -c '^-')
    stale_reason=$(printf 'Stale local branches (>14d, no PR):\n%b\nConsider deleting with: git branch -d <name>' "$stale_lines")
fi

# Output combined report
if [ -n "$orphan_lines" ] && [ -n "$stale_lines" ]; then
    combined=$(printf '%s\n\n%s' "$reason" "$stale_reason")
    jq -n --arg reason "$combined" '{"decision":"allow","reason":$reason}'
elif [ -n "$orphan_lines" ]; then
    jq -n --arg reason "$reason" '{"decision":"allow","reason":$reason}'
elif [ -n "$stale_lines" ]; then
    jq -n --arg reason "$stale_reason" '{"decision":"allow","reason":$reason}'
fi
