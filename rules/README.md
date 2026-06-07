# coding-team/rules/

The **authoritative source** for all rules in this directory is `skills/coding-team/rules/` (this directory).

When `deploy.sh` runs, it creates **relative symlinks** in `~/.claude/rules/` pointing back to these files. There are no copies — one physical file per rule, deployed as a link.

Do not edit rules in `~/.claude/rules/` directly; edit the source here and re-deploy.
