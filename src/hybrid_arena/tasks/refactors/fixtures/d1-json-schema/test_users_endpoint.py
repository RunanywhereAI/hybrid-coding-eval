"""End-to-end tests for POST /users with JSON-schema-style validation."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import run  # noqa: E402
from validate import validate_user  # noqa: E402


def _post(url: str, body) -> tuple[int, dict]:
    data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


@pytest.fixture
def base():
    srv, thread = run(host="127.0.0.1", port=0)
    host, port = srv.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=1)


def test_valid_body_returns_200(base):
    status, payload = _post(f"{base}/users", {"name": "Ada", "age": 36})
    assert status == 200
    assert payload == {"created": {"name": "Ada", "age": 36}}


def test_missing_name_returns_422(base):
    status, payload = _post(f"{base}/users", {"age": 36})
    assert status == 422
    assert "errors" in payload
    fields = {e["field"] for e in payload["errors"]}
    assert "name" in fields


def test_missing_age_returns_422(base):
    status, payload = _post(f"{base}/users", {"name": "Ada"})
    assert status == 422
    fields = {e["field"] for e in payload["errors"]}
    assert "age" in fields


def test_negative_age_returns_422(base):
    status, payload = _post(f"{base}/users", {"name": "Ada", "age": -1})
    assert status == 422
    fields = {e["field"] for e in payload["errors"]}
    assert "age" in fields


def test_non_integer_age_returns_422(base):
    status, payload = _post(f"{base}/users", {"name": "Ada", "age": "old"})
    assert status == 422
    fields = {e["field"] for e in payload["errors"]}
    assert "age" in fields


def test_both_missing_reports_both(base):
    status, payload = _post(f"{base}/users", {})
    assert status == 422
    fields = {e["field"] for e in payload["errors"]}
    assert {"name", "age"}.issubset(fields)


def test_validator_unit_valid():
    assert validate_user({"name": "Ada", "age": 0}) == []


def test_validator_unit_rejects_bool_age():
    errs = validate_user({"name": "Ada", "age": True})
    fields = {e["field"] for e in errs}
    assert "age" in fields


def test_validator_unit_rejects_empty_name():
    errs = validate_user({"name": "", "age": 5})
    fields = {e["field"] for e in errs}
    assert "name" in fields
