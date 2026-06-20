# C3

| ID | Pattern | Check before dispatch |
|----|---------|----------------------|
| C3 | `@tags: ci-config; provable; scope:diff` **CI step runs a venv-dependent tool without an active virtualenv** — `maturin develop`, `pip install -e .`, etc. fail on a clean runner because `actions/setup-python` provides an interpreter, NOT a venv. The job goes red on every push before tests run. Caught on the axon `python-bindings` CI job (TEST-HIGH-3). | Any new/edited CI step invoking `maturin develop` or other venv-requiring tools must create + activate a venv first (`python -m venv .venv && . .venv/bin/activate` in the SAME `run:` block, since each step is a fresh shell — or persist via `$GITHUB_PATH`/`$GITHUB_ENV`). You usually can't run the job locally, so this is a read-time check. |
