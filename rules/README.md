# coding-team/rules/

The **authoritative source** for all rules in this directory is `skills/coding-team/rules/` (this directory).

When `scripts/deploy.sh` runs, it creates **relative symlinks** in `~/.claude/rules/` pointing back to these files. There are no copies — one physical file per rule, deployed as a link.

Do not edit rules in `~/.claude/rules/` directly; edit the source here and re-deploy.

## Cost: everything here is always-loaded

Every `*.md` in this directory (except this README, which `scripts/deploy.sh` skips) is
deployed to `~/.claude/rules/` and loads **unconditionally into every session and
every subagent**. Frontmatter does not change that — `globs:`, `alwaysApply:`,
and `scope:` are all inert; the directory is the entire mechanism.

**Before adding a file here, ask whether it must bind every session.** If it only
needs to reach specific dispatched agents, put it in `reference/` instead and add
an explicit `Read ~/.claude/reference/<name>.md` line to the prompts that need it
— that is the conditional path, and only the dispatched agent pays for it.

Known rationalization: *"extracting duplicated agent-prompt text into `rules/`
de-duplicates it."* It does not. It converts per-agent cost, paid once by one
agent when dispatched, into global cost paid by every session — and leaves the
per-agent read in place. That has already happened twice.
