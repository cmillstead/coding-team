# Agent Standards — Model Routing + UI/UX

Standards that apply to agents dispatched by `/coding-team`. Not loaded outside the coding-team context.

## Model Routing

| Task type | Model | Examples |
|-----------|-------|---------|
| Mechanical | `haiku` | Single file edits, formatting, simple rewrites, grep-and-replace |
| Implementation | `sonnet` | Feature implementation, test writing, multi-file refactoring, debugging |
| Architecture/review | `opus` | Planning, design, spec review, code review, complex debugging |

If a cheaper model fails or returns low-quality results, re-dispatch with the next tier up.

## UI/UX Standards

- **Immediate feedback**: If an action has a delay, always show a loading/progress indicator
- **WCAG 2.1 AA compliance**: Keyboard accessible, color contrast, ARIA labels, focus indicators, semantic HTML, `prefers-reduced-motion` respect
