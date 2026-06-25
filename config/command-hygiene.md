# Command Hygiene

Issue shell commands so they run clean and never trip a permission prompt.

- **One command per Bash call.** Any compound (`;`/`&&`/`||`/`|`, brace groups, subshells) is
  BLOCKED unless it is a plain `VAR=$(single-command)` value-capture — and even those fall through
  to a CC permission prompt (they are never auto-approved). Split compounds into separate Bash calls
  so each command can be reviewed and approved on its own. The Bash tool already returns exit code
  and full output — you never need `set +e`, `$?`, `${PIPESTATUS}`, or `| tail` to capture them.
- **No capture redirects.** Don't redirect to `/tmp/x.log` just to re-read it; the output is already
  in the result. (A command that legitimately must write a file is fine — just not as a capture hack.)
- **Need pipe status?** Use `set -o pipefail` and read the call's own exit code — not `${PIPESTATUS}`,
  which is also zsh/bash-incompatible: lowercase `pipestatus` is zsh, uppercase 0-indexed `PIPESTATUS`
  is bash; the wrong one silently yields an empty exit code.
- **`cd` as its own call**, or rely on the tool's working directory.
- **Never run `nvm`, `nvm use`, or `source ~/.nvm/nvm.sh`.** `source` evaluates arbitrary shell code, so it can NOT be auto-approved (it prompts or dead-ends every time, even though `source` is allow-listed). Non-login shells (including Claude Code tool calls) do not source nvm automatically, so `node`/`npm`/`npx`/`codex` may not be on PATH. If they aren't, use the absolute path: `/Users/cevin/.nvm/versions/node/v20.19.6/bin/node` (or the matching `npm`/`npx`/`codex` in that directory). If the absolute path also fails, report BLOCKED — do not attempt to source nvm.

**Why:** a single allow-listed command (`Bash(pnpm *)`) auto-approves. Compounds (including
`VAR=$(...)` value-captures) do NOT auto-approve — the hook blocks all multi-statement compounds
except value-captures, and value-captures fall through to a CC prompt. Clean single commands = zero
friction; any compound = a prompt or a block every run.
