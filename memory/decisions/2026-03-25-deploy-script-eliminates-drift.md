# Decision: deploy.sh as Single Deployment Mechanism

**Date:** 2026-03-25
**Context:** Agents and hooks existed in two places: the coding-team repo (source of truth) and ~/.claude/ (runtime deployment). Manual copying caused drift — the repo and deployed copies diverged silently.
**Decision:** Created scripts/deploy.sh as the canonical deployment mechanism. It copies agents to ~/.claude/agents/, hooks to ~/.claude/hooks/, and verifies file-by-file that deployed copies match repo copies. The track-artifacts-in-repo.py hook detects drift reactively.
**Rationale:** The drift class of bugs (deployed hook has old code, repo has new code) was responsible for the Case 28 recurrence — the router hook in ~/.claude/ still had the old escape hatch text. A single deployment script eliminates the class entirely.
**Consequences:** All future agent/hook deployments go through deploy.sh. The track-artifacts hook warns when files are written outside the repo. The retro noted that the Case 28 fix was deployed manually instead of through deploy.sh — that's a process gap to close.
