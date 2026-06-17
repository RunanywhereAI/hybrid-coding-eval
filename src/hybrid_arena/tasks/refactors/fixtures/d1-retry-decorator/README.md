# d1-retry-decorator

Exponential-backoff retry decorator applied to a flaky HTTP client.

Files:

- `client.py` — `fetch_json(url)` + server/client exception classes.
- `retry.py` — empty `retry(...)` stub to implement.
- `main.py` — glue: wire `retry(...)` onto `client.fetch_json`.
- `test_retry.py` — pytest suite.

Run tests: `pytest -q`.
