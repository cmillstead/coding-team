#!/usr/bin/env bash
# Deploy coding-team artifacts from repo to ~/.claude/
# Usage: bash scripts/deploy.sh [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE_DIR="$HOME/.claude"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

deploy() {
    local src="$1" dst="$2"
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

echo "Deploy complete."
