#!/bin/bash
# SessionStart hook: detects open PRs with failing CI checks.
# Warns the user about orphan PRs before starting new work.
# All error paths exit 0 silently — only outputs JSON when orphans found.

# Bail silently if gh or jq not available
command -v gh  >/dev/null 2>&1 || exit 0
command -v jq  >/dev/null 2>&1 || exit 0

# Fetch open PRs with status checks (10s timeout)
pr_json=$(timeout 10 gh pr list --author @me --state open \
  --json number,title,statusCheckRollup --limit 20 2>/dev/null) || exit 0

# Exit if empty or not valid JSON
[ -z "$pr_json" ] && exit 0
echo "$pr_json" | jq empty 2>/dev/null || exit 0

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
' 2>/dev/null) || exit 0

# Nothing found — exit silently
[ -z "$orphan_lines" ] && exit 0

# Produce the warning as a decision:allow JSON blob
reason=$(printf 'Open PRs with failing CI:\n%s\nAddress these first — fix CI failures or close with a reason. Starting new work while old PRs rot creates orphan debt.' "$orphan_lines")

jq -n --arg reason "$reason" '{"decision":"allow","reason":$reason}'
