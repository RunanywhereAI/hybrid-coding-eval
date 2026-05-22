# Review — cursor pagination for /items

Overall direction is right: fixed-size pages with a cursor is the
standard fix for an unbounded list endpoint. There are two correctness
bugs and several gaps I'd want addressed before merging.

## 1. Off-by-one: `_decode_cursor` returns the last-served index, but the next page starts at `index + 1`

```python
start = _decode_cursor(cursor) + 1 if cursor else 0
end = start + PAGE_SIZE
...
next_cursor = _encode_cursor(end) if end < len(items) else None
```

The cursor returned to the client is `end` (the first index NOT served
on the current page) but on the next call the code does
`_decode_cursor(cursor) + 1`. That `+ 1` skips the first item of the
next page. Consumers will miss one row at every page boundary.

Pick one convention and stick with it:

- Cursor is "last served index": return `last = start + len(page) - 1`,
  decode with `start = int(cursor) + 1`. Or
- Cursor is "next start": return `end`, decode with `start = int(cursor)`
  (no `+ 1`).

The latter is simpler — delete the `+ 1` on the decode side.

## 2. No upper-bound check — a caller can request `cursor > len(items)`

If a client (or an old saved bookmark) supplies a cursor larger than
`len(items)`, `items[start:end]` silently returns `[]` with
`next_cursor=None` and `start >= len(items)`. That's indistinguishable
from "legitimate end of data", and it hides caller errors.

Add an explicit guard after `_decode_cursor`:

```python
if start < 0 or start > len(items):
    raise HTTPException(status_code=400, detail="cursor out of range")
```

Alternatively sign the cursor (HMAC) so you can detect tampering — the
current plain base64 is security-through-obscurity.

## 3. `int()` on tampered / malformed base64 is caught as `Exception`

The `except Exception:` is too broad — it will swallow programming
errors (e.g. a rename) as "invalid cursor". Narrow to
`(binascii.Error, ValueError, UnicodeDecodeError)`.

## 4. `PAGE_SIZE = 50` is hard-coded

For a list endpoint a client usually wants to pass `limit` (bounded).
Not a blocker, but worth adding a `limit: int = 50` query param with a
ceiling check (`min(limit, MAX_PAGE_SIZE)`).

## 5. Missing tests

This PR ships no test file. Before merge:

- `test_first_page_has_expected_items` — empty cursor returns the first 50.
- `test_cursor_round_trip_covers_all_items` — iterate until
  `next_cursor is None`; assert the concatenated pages equal
  `get_all_items()`. This catches the off-by-one above.
- `test_cursor_out_of_range_returns_400`.
- `test_tampered_cursor_returns_400`.
- `test_exactly_page_size_items_no_next_cursor` — when `len(items) == PAGE_SIZE`
  the first page should return `next_cursor=None`, not a cursor to an empty page.

## 6. Style / minor

- `items: list[dict]` in the response model is loose — use a real
  `Item` model so the OpenAPI schema is useful.
- The old `/items` (unpaginated) is left in place. Is that intentional?
  If it's meant to be removed, do it in this PR; if it's meant to stay,
  mention it in the PR description.

## Recommendation

Request changes. The off-by-one (#1) and unbounded cursor (#2) are both
real bugs that will ship to users. Once those plus tests land, LGTM.
