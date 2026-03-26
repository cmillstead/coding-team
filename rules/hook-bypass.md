# Hook Bypass Rule
If a hook blocks your action, comply — the hook is the authority.
If a hook errors, STOP and report the error to the user.
NEVER work around, bypass, or find alternative approaches to avoid a hook constraint.

Known rationalizations:
- "The hook is broken" — then it needs fixing by the user, not bypassing by you
- "The hook doesn't handle this case" — then the hook needs updating, not circumventing
- "Let me try a different approach" — if the "different approach" avoids the hook, it's a bypass
- "The hook is parsing the input incorrectly" — report the parsing issue; don't exploit it

The hook is the authority. If it's wrong, the user fixes the hook.
