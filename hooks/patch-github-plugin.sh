#!/bin/bash
# Patches the GitHub plugin's .mcp.json to hardcode the PAT,
# replacing the ${GITHUB_PERSONAL_ACCESS_TOKEN} template that
# the sandbox can't resolve.

TOKEN=$(awk '/oauth_token:/ {print $2; exit}' ~/.config/gh/hosts.yml 2>/dev/null | tr -d '[:space:]')
[ -z "$TOKEN" ] && exit 0

for f in \
  ~/.claude/plugins/cache/claude-plugins-official/github/*/.mcp.json \
  ~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/github/.mcp.json; do
  [ -f "$f" ] || continue
  if grep -q 'GITHUB_PERSONAL_ACCESS_TOKEN' "$f" 2>/dev/null; then
    sed -i '' 's/\${GITHUB_PERSONAL_ACCESS_TOKEN}/'"$TOKEN"'/' "$f"
  fi
done
