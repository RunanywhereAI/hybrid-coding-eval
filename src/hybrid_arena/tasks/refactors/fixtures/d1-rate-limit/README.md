# d1-rate-limit

Stdlib-only HTTP app that needs a sliding-window rate-limit middleware.

Files:

- `app.py` — BaseHTTPRequestHandler with `/health` (exempt) and
  `POST /echo` (rate-limited).
- `middleware.py` — empty `RateLimiter` stub for you to implement.
- `test_rate_limit.py` — pytest suite the reference must satisfy.

Run tests: `pytest -q`.
