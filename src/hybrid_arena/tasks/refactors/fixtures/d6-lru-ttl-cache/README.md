# d6-lru-ttl-cache (HARD)

Implement an LRU cache with per-entry TTL eviction. Single-file
solution at `cache.py`. The reference implementation is ~80 LOC and
relies on `collections.OrderedDict` + `time.monotonic`.

Run tests: `pytest -q test_cache.py`. 22 tests covering construction
validation, LRU eviction order, TTL eviction (gated on a
monkeypatched `time.monotonic`), `cache_info()` accounting, and
mixed-eviction edge cases.

The reference lives under `_reference/cache.py` — graders overlay the
model's `cache.py` and run pytest from the directory root.
