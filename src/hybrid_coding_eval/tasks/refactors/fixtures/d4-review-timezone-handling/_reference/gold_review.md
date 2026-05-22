# Review — accept `starts_at` on booking creation

Core idea is fine, but the datetime handling is the kind of bug that
will leak into storage and cause "it worked fine in London, not in
Sydney" tickets forever. Request changes.

## 1. Naive vs aware datetime comparison (merge-blocker)

```python
starts_at = datetime.datetime.fromisoformat(req.starts_at)
...
if starts_at < datetime.datetime.utcnow():
    raise HTTPException(...)
```

Two related problems:

**1a.** `datetime.fromisoformat("2030-01-01T10:00:00")` returns a
**naive** datetime (no `tzinfo`). If the client sends
`"2030-01-01T10:00:00+09:00"` it returns an **aware** datetime.
Comparing a naive to an aware datetime raises `TypeError` at runtime —
so a JST client gets a 500 while a timezone-less client does not. The
two code paths diverge based on input format.

**1b.** `datetime.datetime.utcnow()` is deprecated as of Python 3.12 and
in any case returns a **naive** datetime in UTC's wall-clock time. The
intent of the comparison is "is this timestamp in the past relative to
now, in UTC" — but a naive `starts_at` sent by a Sydney client means
"10 AM local in Sydney"; you're comparing it to "10 AM UTC" and
accepting bookings that have already happened.

**Fix**: always produce an aware UTC datetime from both sides.

```python
from datetime import datetime, timezone

def _parse_utc(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid starts_at") from exc
    if dt.tzinfo is None:
        # Policy choice: either reject, or assume UTC. Reject is safer
        # because it surfaces client bugs instead of silently drifting.
        raise HTTPException(
            status_code=400,
            detail="starts_at must include a timezone offset",
        )
    return dt.astimezone(timezone.utc)
...
starts_at = _parse_utc(req.starts_at)
if starts_at < datetime.now(tz=timezone.utc):
    raise HTTPException(status_code=400, detail="starts_at is in the past")
```

Decide (and document) the policy for no-tz input. Rejecting is the
cleanest answer; if product wants "assume UTC", make that a single line
with `replace(tzinfo=timezone.utc)` and put it in the PR description.

## 2. Validation belongs in the Pydantic model

`starts_at: str` defeats the point of using Pydantic. Either:

```python
class CreateBooking(BaseModel):
    user_id: str
    starts_at: datetime  # Pydantic parses ISO-8601 and attaches tzinfo
```

…or add a `@field_validator("starts_at")` that returns an aware UTC
datetime. Pushing this into the schema gives you consistent 422
responses for malformed input and removes the try/except from the
handler.

## 3. Trailing behaviour: clock skew on "past" check

`starts_at < now()` rejects a booking made for "right now" because by
the time the request is handled, `starts_at` is ~milliseconds past.
Add a small grace window (`now() - timedelta(seconds=5)`) or compare
`<=` depending on product semantics. Name the semantics in code.

## 4. What does `save_booking` store?

If the DB column is `TIMESTAMP WITHOUT TIME ZONE` (Postgres naive),
storing an aware datetime either strips the tz or errors depending on
driver. If it's `TIMESTAMPTZ`, perfect. Worth confirming in the PR
description — this is the other end of the same bug class.

## 5. Tests

The added test uses naive input:

```python
resp = client.post("/bookings", json={"user_id": "u1",
    "starts_at": "2030-01-01T10:00:00"})
```

If the fix in #1 rejects no-tz input, this test needs to send
`"2030-01-01T10:00:00+00:00"`.

Add:

- `test_rejects_datetime_without_timezone` — regression for policy.
- `test_accepts_timezone_offset` — send `+09:00`, assert 201.
- `test_rejects_past_utc_even_if_future_locally` — pick an offset that
  makes a future local time a past UTC time; this proves the
  comparison isn't just string-ordering.
- `test_now_in_past_with_grace_window` — cover the clock-skew decision.

## 6. Minor

- The DTO name `CreateBooking` is fine, but `req: CreateBooking` is a
  little anaemic — consider `payload` or directly destructure fields.
- Log the parsed `starts_at` at INFO so ops can correlate "it rejected
  me" complaints with what the server actually parsed.

## Recommendation

Request changes. Naive/aware comparison (#1) is a real bug that will
misbehave across timezones. After #1 + #2 + regression tests from #5
land, LGTM.
