# Agent Standards — Model Routing + UI/UX

Standards that apply to agents dispatched by `/coding-team`. Not loaded outside the coding-team context.

## Model Routing

| Task type | Model | Examples |
|-----------|-------|---------|
| Mechanical | `haiku` | Single file edits, formatting, simple rewrites, grep-and-replace |
| Implementation | `sonnet` | Feature implementation, test writing, multi-file refactoring, debugging |
| Architecture/review | `opus` | Planning, design, spec review, code review, complex debugging |

**Signals for escalation:**
- Touches 1-2 files with a complete spec → `haiku`
- Touches 3+ files or needs judgment → `sonnet`
- Requires design decisions or broad codebase understanding → `opus`
- If a cheaper model fails or returns low-quality results, re-dispatch with the next tier up.

## UI/UX Standards

- **Immediate feedback**: If an action has a delay, always show a loading/progress indicator
- **WCAG 2.2 AA compliance**: Keyboard accessible, color contrast, ARIA labels, focus indicators, semantic HTML, `prefers-reduced-motion` respect

Note: this file is the source of truth for the WCAG version.
