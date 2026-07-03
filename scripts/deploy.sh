#!/usr/bin/env bash
# Deploy coding-team artifacts from repo to ~/.claude/ as RELATIVE SYMLINKS.
# The source file in the repo is the single authoritative copy; the deployed
# path is just a symlink pointing back to it.
#
# Usage: bash scripts/deploy.sh [--dry-run]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Create a relative symlink at $dst pointing to $src.
# Uses python3 -c os.path.relpath (macOS-safe; no GNU-only tools).
deploy() {
    local src="$1" dst="$2"
    # Compute the relative path from the LINK's directory to the source file.
    local rel
    rel=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))" \
          "$src" "$(dirname "$dst")")

    if $DRY_RUN; then
        echo "[dry-run] ln -s $rel -> $dst"
    else
        mkdir -p "$(dirname "$dst")"
        ln -sfn "$rel" "$dst"
        echo "linked: $rel -> $dst"
    fi
}

# Hooks: *.py and *.sh
for f in "$REPO_ROOT"/hooks/*.py "$REPO_ROOT"/hooks/*.sh; do
    [[ -f "$f" ]] || continue
    deploy "$f" "$CLAUDE_DIR/hooks/$(basename "$f")"
done

# Shared library: symlink the whole _lib/ directory as one unit.
# Remove a real (non-symlink) directory first so ln can create the link.
if [[ -d "$REPO_ROOT/hooks/_lib" ]]; then
    lib_dst="$CLAUDE_DIR/hooks/_lib"
    lib_src="$REPO_ROOT/hooks/_lib"
    lib_rel=$(python3 -c "import os,sys;print(os.path.relpath(sys.argv[1],sys.argv[2]))" \
              "$lib_src" "$(dirname "$lib_dst")")
    if $DRY_RUN; then
        echo "[dry-run] ln -s $lib_rel -> $lib_dst"
    else
        mkdir -p "$(dirname "$lib_dst")"
        # Only remove if it is a real directory (not already a symlink).
        if [[ -d "$lib_dst" && ! -L "$lib_dst" ]]; then
            rm -rf "$lib_dst"
        fi
        ln -sfn "$lib_rel" "$lib_dst"
        echo "linked: $lib_rel -> $lib_dst"
    fi
fi

# Agents: ct-*.md
for f in "$REPO_ROOT"/agents/ct-*.md; do
    [[ -f "$f" ]] || continue
    deploy "$f" "$CLAUDE_DIR/agents/$(basename "$f")"
done

# Prune orphaned agent symlinks: a ct-*.md symlink in CLAUDE_DIR whose repo
# source was deleted (e.g. an agent removed from agents/) is left dangling
# by the loop above, since it only ever adds/updates links. Only ever prune
# a symlink that (a) resolves INTO this repo's agents/ dir (i.e. one we
# created) and (b) whose target no longer exists. A real file, or a
# foreign symlink a user hand-placed pointing elsewhere, is never touched.
for f in "$CLAUDE_DIR"/agents/ct-*.md; do
    [[ -L "$f" ]] || continue

    # Resolve the symlink target to an absolute path (macOS has no
    # `readlink -f`; reuse python3, as the rest of the script already does).
    target_abs=$(python3 -c "import os,sys; d=os.path.dirname(sys.argv[1]); print(os.path.normpath(os.path.join(d, os.readlink(sys.argv[1]))))" "$f")
    case "$target_abs" in
        "$REPO_ROOT/agents/"*) ;;  # ours — eligible for prune
        *) continue ;;             # foreign symlink — never touch
    esac

    [[ -e "$target_abs" ]] && continue

    if $DRY_RUN; then
        echo "[dry-run] rm $f"
    else
        rm -f "$f"
        echo "pruned: $f"
    fi
done

# Rules: *.md (skip README.md — it is deploy meta-doc, not a behavioral rule)
for f in "$REPO_ROOT"/rules/*.md; do
    [[ -f "$f" ]] || continue
    [[ "$(basename "$f")" == "README.md" ]] && continue
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

# Verify all deployed hooks are registered in settings.json or a dispatcher.
# Since D195, UserPromptSubmit hooks may be invoked via prompt-dispatcher.py and
# SessionStart hooks via session-start-dispatcher.py rather than registered
# directly in settings.json — all five registration sites count (PR #101 added
# pretooluse-dispatcher.py and posttooluse-dispatcher.py).
echo "Verifying hook registration..."
SETTINGS="$HOME/.claude/settings.json"
DISPATCHER="$CLAUDE_DIR/hooks/prompt-dispatcher.py"
SESSION_DISPATCHER="$CLAUDE_DIR/hooks/session-start-dispatcher.py"
PRETOOLUSE_DISPATCHER="$CLAUDE_DIR/hooks/pretooluse-dispatcher.py"
POSTTOOLUSE_DISPATCHER="$CLAUDE_DIR/hooks/posttooluse-dispatcher.py"
if [ -f "$SETTINGS" ]; then
    UNREGISTERED=0
    for hook in "$CLAUDE_DIR"/hooks/*.py "$CLAUDE_DIR"/hooks/*.sh; do
        hookname=$(basename "$hook")
        if [ "$hookname" = "__init__.py" ] || [ "$hookname" = "_lib" ]; then
            continue
        fi
        if grep -q "$hookname" "$SETTINGS"; then
            continue
        fi
        if [ -f "$DISPATCHER" ] && grep -q "$hookname" "$DISPATCHER"; then
            continue
        fi
        if [ -f "$SESSION_DISPATCHER" ] && grep -q "$hookname" "$SESSION_DISPATCHER"; then
            continue
        fi
        if [ -f "$PRETOOLUSE_DISPATCHER" ] && grep -q "$hookname" "$PRETOOLUSE_DISPATCHER"; then
            continue
        fi
        if [ -f "$POSTTOOLUSE_DISPATCHER" ] && grep -q "$hookname" "$POSTTOOLUSE_DISPATCHER"; then
            continue
        fi
        echo "  WARNING: $hookname deployed but not registered in settings.json or a dispatcher"
        UNREGISTERED=$((UNREGISTERED + 1))
    done
    if [ "$UNREGISTERED" -eq 0 ]; then
        echo "  All hooks registered."
    fi
fi

echo "Deploy complete."
