# Command Hygiene

Issue shell commands so they run clean and never trip a permission prompt.

- **One command per Bash call is RECOMMENDED best practice** — cleaner review, a per-command exit
  code and output, and no prompt friction. The compound block (`;`/`&&`/`||`/`|`, brace groups,
  subshells) is operator-toggleable via `GIT_SAFETY_ALLOW_COMPOUND`, currently set to `1` in
  settings.json: with the flag on, the compound block is disabled UNCONDITIONALLY — every
  multi-statement compound falls through to CC's normal permission handling (allowlist prompt or
  pass) — it is not auto-approved. This includes a command that references a literal `git` token
  anywhere (e.g. inside a quoted free-text argument, or a plain `git status ... | head`) — a `git`
  token no longer re-triggers the block. Recognized `git add`/`commit`/`push`/`merge` still go
  through the usual secret/branch/format checks earlier in the hook (unaffected by this toggle). A
  plain `VAR=$(single-command)` value-capture always falls through to a CC permission prompt
  regardless of the flag (never auto-approved). Split compounds into separate Bash calls when you
  want each command reviewed and approved on its own. The Bash tool already returns exit code and
  full output — you never need `set +e`, `$?`, `${PIPESTATUS}`, or `| tail` to capture them.
- **No capture redirects.** Don't redirect to `/tmp/x.log` just to re-read it; the output is already
  in the result. (A command that legitimately must write a file is fine — just not as a capture hack.)
- **Need pipe status?** Use `set -o pipefail` and read the call's own exit code — not `${PIPESTATUS}`,
  which is also zsh/bash-incompatible: lowercase `pipestatus` is zsh, uppercase 0-indexed `PIPESTATUS`
  is bash; the wrong one silently yields an empty exit code.
- **Every repo-scoped call carries its own absolute `cd`** — `cd /abs/path && <command>`. The tool's working directory PERSISTS between calls and the result never reports where it ran, so a bare `git`/`find`/`grep` silently answers from whichever directory a previous call left behind. In a tree with submodules (`~/.claude` and `~/.claude/skills/coding-team` share `agents/`, `hooks/`, `docs/plans/`) that wrong-repo answer is well-formed and plausible — it reads exactly like a real result. This compound is exempt from the one-command-per-call preference above: with `GIT_SAFETY_ALLOW_COMPOUND: "1"` it costs no prompt in practice, and a silent wrong-repo read costs far more. Never carry a working directory forward from an earlier call, and never trust a surprising repo-scoped result (a file missing, a grep clean, a log short) until you re-run it with an explicit `cd`.
- **Never run `nvm`, `nvm use`, or `source ~/.nvm/nvm.sh`.** `source` evaluates arbitrary shell code, so it can NOT be auto-approved (it prompts or dead-ends every time, even though `source` is allow-listed). Non-login shells (including Claude Code tool calls) do not source nvm automatically, so `node`/`npm`/`npx`/`codex` may not be on PATH. If they aren't, use the absolute path: `/Users/cevin/.nvm/versions/node/v20.19.6/bin/node` (or the matching `npm`/`npx`/`codex` in that directory). If the absolute path also fails, report BLOCKED — do not attempt to source nvm.

**Why:** a single allow-listed command (`Bash(pnpm *)`) auto-approves. A compound falls through to
CC's normal permission handling only while `GIT_SAFETY_ALLOW_COMPOUND` is on; `VAR=$(...)`
value-captures always fall through to a CC prompt regardless. Clean single commands = zero friction;
a compound MAY cost a prompt (or a block, when the flag is off), but with the flag on it often just
passes — the `cd <abs> && <command>` form above is the case where it reliably does.
