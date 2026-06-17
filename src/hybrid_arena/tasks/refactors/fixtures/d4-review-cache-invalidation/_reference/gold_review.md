# Review — Redis cache for `get_user_settings`

There is a **cross-tenant data-leak bug** in the cache key that will
serve one tenant's settings to another. This is a security issue, not a
style nit — it needs to block the merge.

## 1. Cache key omits `tenant_id` — cross-tenant data leak

```python
cache_key = f"settings:user:{user_id}"
```

The underlying query filters on `(user_id, tenant_id)`, i.e. the data
depends on BOTH parameters. But the cache key only includes `user_id`.

Concrete failure: a user `u1` can belong to tenant `A` and tenant `B`
(this is normal in multi-tenant SaaS). Sequence:

1. `get_user_settings(u1, tenant=A)` → MISS → DB returns A-specific
   settings → cache stores under `settings:user:u1`.
2. `get_user_settings(u1, tenant=B)` → HIT on the same key → returns
   A's settings to a B-context caller.

This is a classic cache-key aliasing vulnerability. **Fix:** include
every parameter the underlying query depends on:

```python
cache_key = f"settings:user:{tenant_id}:{user_id}"
```

Use `:` delimiters (or a hash) so a malicious `user_id`
containing `:` can't collide onto another tenant's key. If user IDs are
opaque UUIDs this is fine; otherwise hash them.

Similarly, `invalidate_user_settings(user_id)` must take a `tenant_id`
too — currently it would try to delete the single-argument key that no
longer exists after the fix, silently succeeding.

## 2. `json` is used but not imported

```python
if cached is not None:
    return json.loads(cached)
```

The diff imports `redis_client` but not `json`. The import list at the
top of the file is missing it. This will fail at runtime on the first
cache hit. Add `import json`.

## 3. No negative-caching guard rails

`data = row.as_dict() if row else {}` caches an **empty dict** on a
miss. That's arguably desired (avoids the DB on every 404) but:

- TTL is 5 minutes. If a new settings row is created immediately after a
  miss, the user sees `{}` for up to 5 minutes. Is that acceptable?
- The invalidation endpoint exists but isn't wired into the settings
  write path (the PR doesn't touch `update_user_settings` or wherever
  the rows are created). Stale data is guaranteed until TTL elapses.

Action: either call `invalidate_user_settings` from every write path, or
use a write-through pattern (update Redis inside the write transaction
commit callback). State explicitly in the PR description how stale data
is bounded.

## 4. `invalidate_user_settings` route has no authz

```python
@router.post("/settings/invalidate")
def clear_settings(user_id: str):
    invalidate_user_settings(user_id)
```

Anyone can POST arbitrary user IDs and force a cache miss for them.
That's a cheap denial-of-wallet (every victim's next read hits the DB)
and possibly a cache-stampede vector. Require an authenticated
admin/owner token and scope to the caller's own user_id.

## 5. Cache stampede / thundering herd

When the TTL expires on a hot row, N concurrent requests all miss
simultaneously and hit the DB. For 5-minute TTL + low write volume this
might be fine, but name the assumption. A `SET NX` lock around the
refill (or `redis.cache` middleware with coalescing) is the standard
mitigation.

## 6. Missing tests

The PR ships no tests. Before merge:

- `test_hit_returns_cached_value` — prime the cache, assert DB is not
  queried.
- `test_cross_tenant_isolation` — set tenant A for user u1, then read
  as tenant B; assert the returned settings match tenant B's row, not
  A's. This is the regression test for bug #1.
- `test_miss_populates_cache`.
- `test_invalidate_removes_key` — including the tenant-scoped key shape.
- `test_empty_row_is_cached_as_empty_dict` (or change the policy).

## Recommendation

Request changes. Bug #1 is a security/correctness defect and must be
fixed before this ships. Bug #2 (missing import) is also merge-blocking
but trivial. Everything else is merge-gating hygiene (tests, authz).
