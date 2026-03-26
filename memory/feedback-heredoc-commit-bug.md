---
name: HEREDOC commit message parsing — fixed
description: git-safety-guard now handles -F/--file= and HEREDOC patterns; block-by-default on unparseable messages; bypass rationalization added
type: feedback
---

git-safety-guard.py's commit message format check previously only parsed `-m "text"` patterns. HEREDOC (`-m "$(cat <<'EOF'...)"`) and file-based (`-F file`) commits bypassed validation entirely because `extract_commit_message` returned `None` and the check silently passed.

**Fixed (2026-03-26):**
1. `extract_commit_message` now handles `-F`/`--file=` (reads file contents) and HEREDOC patterns
2. Block-by-default: unparseable `git commit` commands are blocked, not passed
3. `--amend --no-edit` is exempted (no new message to validate)
4. Named rationalization added: "The hook is parsing incorrectly" — fix the message, not the command format

**How to apply:** No workaround needed. Use `git commit -m "feat: ..."` or `git commit -F /tmp/msg.txt` with a properly prefixed message. Both are now validated.
