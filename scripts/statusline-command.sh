#!/usr/bin/env bash
# Claude Code status line
# Format: branch | Model Name | [████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 13%

input=$(cat)

# Git branch (skip optional locks)
branch=$(git -C "$(echo "$input" | jq -r '.workspace.current_dir // .cwd')" \
    --no-optional-locks branch --show-current 2>/dev/null)
[ -z "$branch" ] && branch="no-branch"

# Model display name
model=$(echo "$input" | jq -r '.model.display_name // .model.id // "unknown"')

# Context window usage
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')

# Build visual bar (33 chars wide) with green/yellow/red coloring
BAR_WIDTH=33
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
DIM='\033[2m'
RESET='\033[0m'
if [ -n "$used_pct" ]; then
    filled=$(echo "$used_pct $BAR_WIDTH" | awk '{printf "%d", int($1 * $2 / 100 + 0.5)}')
    empty=$(( BAR_WIDTH - filled ))
    # Thresholds: green <50%, yellow 50-80%, red >80% (compaction ~80%)
    if [ "$used_pct" -ge 80 ] 2>/dev/null; then
        color="$RED"
    elif [ "$used_pct" -ge 50 ] 2>/dev/null; then
        color="$YELLOW"
    else
        color="$GREEN"
    fi
    bar=""
    for i in $(seq 1 "$filled"); do bar="${bar}█"; done
    empty_bar=""
    for i in $(seq 1 "$empty"); do empty_bar="${empty_bar}░"; done
    ctx_part="${color}[${bar}${DIM}${empty_bar}${RESET}${color}] ${used_pct}%${RESET}"
else
    ctx_part=""
fi

# Codesight active indicator (preserve existing behaviour)
ACTIVE_FILE="/tmp/codesight-active"
STALE_SECONDS=30
cs_part=""
if [ "${CODESIGHT_STATUSLINE:-1}" != "0" ] && [ -f "$ACTIVE_FILE" ]; then
    ts=$(cat "$ACTIVE_FILE" 2>/dev/null)
    now=$(date +%s)
    if [ -n "$ts" ] && [ $(( now - ${ts%.*} )) -lt "$STALE_SECONDS" ]; then
        cs_part=" \033[32mCS\033[0m"
    else
        rm -f "$ACTIVE_FILE"
    fi
fi

# Coding-team active indicator — lit when exactly one in-progress plan exists
ct_part=""
CT_MAIN_ROOT=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's|/.git$||')
if [ -n "$CT_MAIN_ROOT" ] && [ -d "$CT_MAIN_ROOT/docs/plans" ]; then
    in_progress_count=0
    for plan in "$CT_MAIN_ROOT/docs/plans"/*.md; do
        [ -r "$plan" ] || continue
        # Frontmatter must start at byte 0 (matching Python helper); check for status: in-progress
        # Use sprintf %c for BOM (portable: BSD awk regex does not interpret \xNN escapes)
        if awk '
            BEGIN{n=0; bom=sprintf("%c%c%c", 239, 187, 191)}
            NR==1 {
                if (substr($0, 1, 3) == bom) $0 = substr($0, 4)
                if ($0 !~ /^---[[:space:]]*$/) exit 1
                n=1
                next
            }
            n==1 && /^---[[:space:]]*$/ {exit}
            n==1 && /^status:[[:space:]]*in-progress[[:space:]]*$/ {found=1}
            END {exit !found}
        ' "$plan" 2>/dev/null; then
            in_progress_count=$((in_progress_count + 1))
        fi
    done
    if [ "$in_progress_count" -eq 1 ]; then
        ct_part=" \033[32m█\033[0m"
    elif [ "$in_progress_count" -gt 1 ]; then
        ct_part=" \033[31m!\033[0m"
    fi
fi

# Assemble output
parts="$branch | $model"
[ -n "$ctx_part" ] && parts="${parts} | ${ctx_part}"

printf "%b%b%b" "$parts" "$cs_part" "$ct_part"
