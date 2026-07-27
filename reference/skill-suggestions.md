# Proactive Skill Suggestions

Suggest the right skill at natural transition points — don't wait to be asked:

| When you notice... | Suggest |
|---|---|
| Feature implementation complete, about to commit/PR | `/scan-code` before the PR |
| Security-sensitive code changed (auth, crypto, input handling) | `/scan-security` |
| Scan findings exist with an implementation plan | `/scan-fix` to remediate atomically |
| Previous scan findings may not be verified | `/scan-previous` |
| New user-facing feature or UX change | `/scan-product` |
| High-stakes code (payments, permissions, data deletion) | `/scan-adversarial` |
| Production incident, outage, or urgent bug in prod | `agency-engineering-incident-response-commander` for structured response |
| New to a codebase, or onboarding someone | `/onboard` for guided orientation |
| Dependencies haven't been checked in a while | `/dep-audit` before the next release |
| Shipping breaking changes to consumers | `/migration-guide` alongside the release |
| Docs are thin, missing, or mediocre | `/doc-write` to create or elevate |
| Feedback memory could be a hook | `/harness-engineer` to evaluate promotion |
| Harness hasn't been audited recently | `/harness-engineer audit` for maturity check |
| UI/screen/component change | `/a11y` |
| New/changed API endpoint | `/api-qa` |
