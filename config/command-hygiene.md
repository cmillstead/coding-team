# Command Hygiene

Issue shell commands so they run clean and never trip a permission prompt.

- **Chain only allowlisted atoms.** A compound (`;`/`&&`/`||`/`|`, or `VAR=$(...)`) is fine ONLY
  when every command in it is already allowlisted — those auto-approve via the `compound_allow`
  fold. A compound that hides any unrecognized command must be split so the unknown command runs as
  its own Bash call (reviewed in isolation); if you don't, you'll get a hygiene `ask` reminder. The
  Bash tool already returns exit code and full output — you never need `set +e`, `$?`,
  `${PIPESTATUS}`, or `| tail` to capture them.
- **No capture redirects.** Don't redirect to `/tmp/x.log` just to re-read it; the output is already
  in the result. (A command that legitimately must write a file is fine — just not as a capture hack.)
- **Need pipe status?** Use `set -o pipefail` and read the call's own exit code — not `${PIPESTATUS}`,
  which is also zsh/bash-incompatible: lowercase `pipestatus` is zsh, uppercase 0-indexed `PIPESTATUS`
  is bash; the wrong one silently yields an empty exit code.
- **`cd` as its own call**, or rely on the tool's working directory.

**Why:** a single allow-listed command (`Bash(pnpm *)`) auto-approves — and so does a compound whose
every atom is allow-listed (the `compound_allow` fold). What still trips a prompt is a compound that
hides an *unrecognized* atom: the per-atom allowlist can't match it, so it's surfaced for review (now
with a hygiene `ask` reminder naming the atom to isolate). Clean single commands or all-allowlisted
compounds = zero friction; an improvised compound with an unknown command = a prompt every run.
