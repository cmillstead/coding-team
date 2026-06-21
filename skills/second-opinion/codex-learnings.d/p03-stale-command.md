# P3

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| P3 | `@tags: plan-symbol; command-grammar; reasoning-shape; scope:plan; floor` **Stale command** — a shell/CLI command whose flags or subcommands no longer exist | Run `--help` (or check the CLI source) for every command the plan tells someone to run. Flags drift; verify the exact invocation. |

**Design default:** Run `--help` or check the CLI source for every command and flag the plan specifies — never include a shell invocation without verifying the exact flag spelling exists in the current version.
