# C1

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| C1 | `@tags: path-input; provable; scope:diff` **Single-gate path trust boundary** — validating a path-shaped field with one rule (e.g. `if value.contains("/")`) lets slashless inputs (`".."`, `"tmp"`, `"src"`) bypass the check and resolve against cwd. Caught as a CRITICAL slashless-bypass in the codesight MCP build. | Classify every path-shaped field into three tiers and validate accordingly: **(1) Identifier** (`repo` accepting `"engram"` OR an absolute path) — only path-form gets the prefix check. **(2) Filesystem path** (`path`, `repoPath`, `storagePath`) — ALWAYS `path.resolve` + require result under the trusted prefix, slash or not. **(3) Repo-relative** (`filePath`, `pathPrefix`) — reject any `..` segment via `path.posix.normalize` + segment split. Ask "identifier or filesystem path?" for each field; the rules differ. |

**Design default:** When a task spec introduces a path-shaped field, classify it as identifier / filesystem-path / repo-relative and state the validation tier for each — never a lone `contains('/')` check.
