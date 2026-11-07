# devagent benchmark

15 small but real coding tasks (10 features, 5 bug fixes) on two practice projects, graded by tests
that devagent never sees.

| Project | What it is | Tasks |
|---|---|---|
| [textkit](projects/textkit) | Text helpers | slugify, truncate, palindrome, word wrap, word frequencies, camelCase → snake_case, Roman numerals |
| [shop](projects/shop) | Cart and inventory, with 2 planted bugs | 2 bug reports, discount validation, remove items, tax with half-up rounding, JSON save/load, low-stock report, shipping rules |

## How a task is graded

1. The project is copied to a fresh git repo.
2. devagent gets **only the one-sentence task** (`tasks/<id>/task.toml`) and runs with `--yes --no-deploy`.
3. After it finishes, the harness copies in **`hidden_test.py`**, which devagent never saw, and runs
   the whole suite inside the test sandbox.
4. **Solved** = the hidden tests *and* the project's own tests pass.

The harness also records cost, time, debug attempts, and **false success**: devagent said its tests
passed, but the hidden tests failed. That number shows how much you can trust devagent's own green ✅.

## The tasks are checked to be fair

`python -m bench.run validate` (also run in CI by [tests/test_bench.py](../tests/test_bench.py)) checks
every task:
- The starting project's tests pass.
- The hidden tests **fail** before any change, so the task isn't already solved.
- A **reference solution** (`tasks/<id>/solution/`) passes them, so the task is possible and the task
  sentence gives everything the tests check.

## Running it

```bash
.venv/bin/python -m bench.run validate               # free, no API calls
.venv/bin/python -m bench.run run --tasks 01         # one task (about $0.50)
.venv/bin/python -m bench.run run                    # all 15 tasks
.venv/bin/python -m bench.run report bench/results/<file>.json
```

Results are saved to `results/` as JSON and as a Markdown table. The agents' working folders and
logs are kept in `.work/` for inspection.

## Results

No results yet. Numbers will appear here only from real runs, never estimated.
