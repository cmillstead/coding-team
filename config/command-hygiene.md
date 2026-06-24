# Command Hygiene

Issue shell commands so they run clean and never trip a permission prompt.

- **One command per Bash call.** The Bash tool already returns the exit code and full output — you do
  not need `set +e`, `$?`, `${PIPESTATUS}`, or `| tail` to capture them. Read them from the result.
- **No compound wrappers for verification.** Run each gate as its own call: `pnpm --filter db
  test:voice`, then `pnpm --filter web typecheck`, then lint — separately, not chained.
- **No capture redirects.** Don't redirect to `/tmp/x.log` just to re-read it; the output is already
  in the result. (A command that legitimately must write a file is fine — just not as a capture hack.)
- **Need pipe status?** Use `set -o pipefail` and read the call's own exit code — not `${PIPESTATUS}`,
  which is also zsh/bash-incompatible: lowercase `pipestatus` is zsh, uppercase 0-indexed `PIPESTATUS`
  is bash; the wrong one silently yields an empty exit code.
- **`cd` as its own call**, or rely on the tool's working directory.

**Why:** a single allow-listed command (`Bash(pnpm *)`) auto-approves. The instant you wrap commands
into a compound — chaining (`;`/`&&`/`|`), redirects (`>`), or brace/`$?` expansions — the per-command
allowlist no longer applies and the brace/expansion safety classifier prompts *regardless* of
settings. Clean single commands = zero friction; compound improvised blocks = a prompt every run.
