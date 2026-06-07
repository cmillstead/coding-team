#!/usr/bin/env bash
# Deploy coding-team artifacts from repo to ~/.claude/
# Usage: bash scripts/deploy.sh [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Accumulate repo-relative paths of every file deployed to $CLAUDE_DIR.
# Populated by the deploy() function; used to rewrite the .gitignore block.
DEPLOYED_PATHS=()

deploy() {
    local src="$1" dst="$2"
    # Record repo-relative destination (strip CLAUDE_DIR prefix + leading slash)
    local rel_dst="${dst#$CLAUDE_DIR/}"
    DEPLOYED_PATHS+=("$rel_dst")
    if $DRY_RUN; then
        echo "[dry-run] $src -> $dst"
    else
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        chmod +x "$dst" 2>/dev/null || true
        echo "deployed: $src -> $dst"
    fi
}

# Hooks: *.py and *.sh
for f in "$REPO_ROOT"/hooks/*.py "$REPO_ROOT"/hooks/*.sh; do
    [[ -f "$f" ]] || continue
    deploy "$f" "$CLAUDE_DIR/hooks/$(basename "$f")"
done

# Shared library: _lib/
if [[ -d "$REPO_ROOT/hooks/_lib" ]]; then
    mkdir -p "$CLAUDE_DIR/hooks/_lib"
    for f in "$REPO_ROOT"/hooks/_lib/*.py; do
        [[ -f "$f" ]] || continue
        deploy "$f" "$CLAUDE_DIR/hooks/_lib/$(basename "$f")"
    done
fi

# Agents: ct-*.md
for f in "$REPO_ROOT"/agents/ct-*.md; do
    [[ -f "$f" ]] || continue
    deploy "$f" "$CLAUDE_DIR/agents/$(basename "$f")"
done

# Rules: *.md
for f in "$REPO_ROOT"/rules/*.md; do
    [[ -f "$f" ]] || continue
    deploy "$f" "$CLAUDE_DIR/rules/$(basename "$f")"
done

# Global config: CLAUDE.md, golden-principles.md, code-style.md
for f in "$REPO_ROOT"/config/*.md; do
    [[ -f "$f" ]] || continue
    deploy "$f" "$CLAUDE_DIR/$(basename "$f")"
done

# Scripts (statusline etc)
if [[ -f "$REPO_ROOT/scripts/statusline-command.sh" ]]; then
    deploy "$REPO_ROOT/scripts/statusline-command.sh" "$CLAUDE_DIR/statusline-command.sh"
fi

# ---------------------------------------------------------------------------
# Rewrite the managed .gitignore block in $CLAUDE_DIR/.gitignore
# so deployed artifacts are never dual-tracked in the claude-harness repo.
#
# Block markers:
#   # BEGIN deploy-managed (...)
#   <sorted unique relative paths>
#   # END deploy-managed
#
# Idempotent: replace the block in place if it already exists, else append.
# ---------------------------------------------------------------------------
BEGIN_MARKER="# BEGIN deploy-managed (coding-team deploy.sh artifacts — derived from skills/coding-team; do not edit by hand)"
END_MARKER="# END deploy-managed"

# Build the sorted, unique block content from DEPLOYED_PATHS
block_content() {
    # Sort and deduplicate the accumulated paths, one per line
    printf '%s\n' "${DEPLOYED_PATHS[@]}" | sort -u
}

GITIGNORE="$CLAUDE_DIR/.gitignore"

if $DRY_RUN; then
    echo ""
    echo "[dry-run] Would write .gitignore block to $GITIGNORE:"
    echo "$BEGIN_MARKER"
    block_content
    echo "$END_MARKER"
else
    # Build the new block as a variable
    new_block="$BEGIN_MARKER
$(block_content)
$END_MARKER"

    if [[ ! -f "$GITIGNORE" ]]; then
        # No .gitignore yet — create it with just the block
        printf '%s\n' "$new_block" > "$GITIGNORE"
        echo "Created $GITIGNORE with deploy-managed block."
    else
        # Check whether the block already exists by looking for the BEGIN marker
        if grep -qF "$BEGIN_MARKER" "$GITIGNORE"; then
            # Replace the existing block in place using awk (macOS-safe, no GNU sed -i)
            awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" -v block="$new_block" '
                BEGIN { in_block = 0; printed = 0 }
                $0 == begin {
                    in_block = 1
                    if (!printed) {
                        print block
                        printed = 1
                    }
                    next
                }
                in_block && $0 == end {
                    in_block = 0
                    next
                }
                in_block { next }
                { print }
            ' "$GITIGNORE" > "$GITIGNORE.tmp" && mv "$GITIGNORE.tmp" "$GITIGNORE"
            echo "Updated deploy-managed block in $GITIGNORE."
        else
            # Append the block (preserve existing content)
            printf '\n%s\n' "$new_block" >> "$GITIGNORE"
            echo "Appended deploy-managed block to $GITIGNORE."
        fi
    fi
fi

# Verify all deployed hooks are registered in settings.json
echo "Verifying hook registration..."
SETTINGS="$HOME/.claude/settings.json"
if [ -f "$SETTINGS" ]; then
    UNREGISTERED=0
    for hook in "$CLAUDE_DIR"/hooks/*.py "$CLAUDE_DIR"/hooks/*.sh; do
        hookname=$(basename "$hook")
        if [ "$hookname" = "__init__.py" ] || [ "$hookname" = "_lib" ]; then
            continue
        fi
        if ! grep -q "$hookname" "$SETTINGS"; then
            echo "  WARNING: $hookname deployed but not registered in settings.json"
            UNREGISTERED=$((UNREGISTERED + 1))
        fi
    done
    if [ "$UNREGISTERED" -eq 0 ]; then
        echo "  All hooks registered."
    fi
fi

echo "Deploy complete."
