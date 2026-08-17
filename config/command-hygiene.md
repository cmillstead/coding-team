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
- **Never `cd`. Name the absolute path inside the command** — `git -C /abs/repo status`, `grep -n 'pat' /abs/path/file`, `find /abs/path -name '*.md'`. The tool's working directory PERSISTS between calls and the result never reports where it ran, so a bare `git`/`find`/`grep` silently answers from whichever directory an earlier call left behind. Where `~/.claude` and `~/.claude/skills/coding-team` share `agents/`, `hooks/`, `docs/plans/`, that wrong-repo answer is well-formed and plausible — it reads exactly like a real result. Known rationalization: "I'll just `cd` there first" — `cd /abs && <command>` is NOT the fix, it is the cause: using it once arms the trap for every later call that omits it, which is why the drift happens at all. Naming the path mutates nothing and needs no compound, and a call that omits it cannot poison the next call the way a `cd` does. When the command has no path flag at all, use one anyway if it exists (`pytest /abs/path/test.py`, `npm --prefix /abs`, `cargo --manifest-path /abs/Cargo.toml`); only for a script that must run from its own root (`./check.sh`) wrap it so the move dies with the call — `(cd /abs/path && ./check.sh)`. Never a bare `cd`, and never `cd` as its own call. Measured 2026-08-11: two agents reading this very rule while implementing it omitted the prefix seven times between them, so treat "I'll remember" as already falsified. Never trust a surprising repo-scoped result (a file missing, a grep clean, a log short) until you re-run it with the path named.
- **Never run `nvm`, `nvm use`, or `source ~/.nvm/nvm.sh`.** `source` evaluates arbitrary shell code, so it can NOT be auto-approved (it prompts or dead-ends every time, even though `source` is allow-listed). Non-login shells (including Claude Code tool calls) do not source nvm automatically, so `node`/`npm`/`npx`/`codex` may not be on PATH. If they aren't, use the absolute path: `/Users/cevin/.nvm/versions/node/v20.19.6/bin/node` (or the matching `npm`/`npx`/`codex` in that directory). If the absolute path also fails, report BLOCKED — do not attempt to source nvm.

**Why:** a single allow-listed command (`Bash(pnpm *)`) auto-approves. A compound falls through to
CC's normal permission handling only while `GIT_SAFETY_ALLOW_COMPOUND` is on; `VAR=$(...)`
value-captures always fall through to a CC prompt regardless. Clean single commands = zero friction;
a compound MAY cost a prompt (or a block, when the flag is off). Naming the path inside a single
command sidesteps the question entirely — there is no compound to fall through.

## File ownership

- `code-style.md`, `command-hygiene.md`, and `golden-principles.md` exist at the `~/.claude` root
  ONLY as relative symlinks into `skills/coding-team/config/` — the root paths are links, not files.
- Their real content is tracked in the `cmillstead/coding-team` submodule, NOT `claude-harness`.
- Consequence: editing any of the three surfaces only as `M skills/coding-team` in `~/.claude` git
  status, and they ship via a coding-team PR + a parent gitlink bump — never a plain claude-harness PR.
