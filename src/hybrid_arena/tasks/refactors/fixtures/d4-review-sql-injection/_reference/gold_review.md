# Review — `search` filter for `/reports`

This PR is a SQL injection. It must not merge in its current form.

## 1. SQL injection in the `search` parameter (merge-blocker, security)

```python
if search:
    where = f" WHERE title LIKE '%{search}%'"
sql = text(
    "SELECT id, title, created_at FROM reports"
    + where
    + f" ORDER BY created_at DESC LIMIT {limit}"
)
```

`search` is a raw query-string value interpolated into the SQL with an
f-string. An attacker can send e.g.

```
/reports?search=%25%27%3B DROP TABLE reports%3B --
```

…or more realistically a UNION-based exfiltration payload, because
`sqlalchemy.text()` does **not** escape the string — it just marks it
as raw SQL. This is textbook SQLi.

Fix: use a bound parameter. SQLAlchemy's `text()` supports `:name` binds:

```python
stmt = text(
    "SELECT id, title, created_at FROM reports"
    + (" WHERE title LIKE :pattern" if search else "")
    + " ORDER BY created_at DESC LIMIT :limit"
)
params = {"limit": limit}
if search:
    # Escape LIKE wildcards in user input, then add the wildcards ourselves.
    escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    params["pattern"] = f"%{escaped}%"
rows = conn.execute(stmt, params).mappings().all()
```

Two things to notice:

1. Binds handle the injection (primary fix).
2. `%` and `_` are wildcards in `LIKE`. Without escaping, a caller
   passing `50%` or `a_b` gets surprising matches. Escape them, and pass
   `ESCAPE '\\'` if your dialect needs it explicit (Postgres doesn't).

## 2. `limit` is also interpolated

```python
+ f" ORDER BY created_at DESC LIMIT {limit}"
```

FastAPI's type coercion (`limit: int = 50`) makes this *currently* safe
because a non-int 422s before reaching this line, but relying on that
defense-in-depth is fragile — the next refactor that loosens the type
(e.g. `limit: str` for "50,100") re-opens the hole. Bind it too
(`:limit` as shown above). Also add an explicit upper bound
(`limit = min(limit, 500)`), otherwise `?limit=100000000` is a trivial
DoS against the DB.

## 3. The new test does not prove the fix works

```python
def test_list_with_search_filter(client):
    resp = client.get("/reports?search=hello")
    assert resp.status_code == 200
```

A 200 doesn't tell you the query was safe. Add regression tests:

- `test_search_does_not_allow_sql_injection` — pass
  `"'; DROP TABLE reports; --"` and assert (a) response is 200, (b) the
  reports table still exists, (c) the result set is empty (or whatever
  the benign behaviour is). This is the test that would have caught
  this PR.
- `test_search_matches_substring` — seed two rows with titles
  `"monthly report"` and `"weekly update"`, call `?search=monthly`, assert
  you get exactly the first row.
- `test_search_escapes_like_wildcards` — seed titles `"50% off"` and
  `"50 dollars"`, call `?search=50%25` (URL-escaped `%`), assert you
  get only `"50% off"`.

## 4. Minor

- Consider extracting the query builder into a function you can unit
  test without spinning up FastAPI.
- The whitespace-prefixed `WHERE` concat is brittle. If you have more
  filters coming, switch to SQLAlchemy Core (`select().where()`) — the
  Expression Language is the whole point of using SQLAlchemy.
- No `limit` lower bound either. `?limit=-1` is probably a 500.

## Recommendation

Request changes. The SQLi (#1) is a blocker; the `limit` interpolation
(#2) should be fixed in the same PR; add the regression test (#3) so
this class of bug can't recur.
