# d1-json-schema

Add JSON-schema-style body validation to `POST /users`.

Files:

- `app.py` — stdlib HTTP server with the endpoint (already calls
  `validate_user`; don't change it unless needed).
- `validate.py` — the empty validator stub to implement.
- `test_users_endpoint.py` — pytest suite.

Run tests: `pytest -q`.
