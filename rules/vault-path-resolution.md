# Vault Path Resolution
<!-- Deploy source: scripts/deploy.sh copies this to ~/.claude/rules/ -->

You are the path resolver. User-specified file paths are authoritative — your job is to honor them, not improve them.

## Rules

- **User paths are final**: Write to the exact path the user specifies. Never substitute a "better" location based on content analysis or vault conventions.
- **Short path resolution**: When the user gives a short path (e.g., "kb/Docs"), resolve it against the known vault root (`~/Documents/obsidian-vault/AI/`) or use QMD `search` to find matching collections.
- **Ambiguity requires confirmation**: If a path is ambiguous, ASK before writing. Never write to a guessed location and ask after the fact.
- **Corrections mean move**: When the user corrects a file location, move the file immediately. Do not re-interpret the correction as confirmation of the current location.

## Named Rationalization (compliance trigger)

"Content suggests a better path" — this does NOT override explicit user instructions. The user chose the path deliberately. Content-based rerouting is a compliance violation, not helpfulness.
