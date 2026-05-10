"""Reference body validator for ``POST /users``.

Returns a list of ``{"field", "error"}`` dicts; empty list means valid.
"""

from __future__ import annotations

from typing import Any


def validate_user(body: Any) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    if not isinstance(body, dict):
        errors.append({"field": "body", "error": "must be a JSON object"})
        return errors

    # --- name ---
    if "name" not in body:
        errors.append({"field": "name", "error": "required"})
    else:
        name = body["name"]
        if not isinstance(name, str) or isinstance(name, bool):
            errors.append({"field": "name", "error": "must be a string"})
        elif not name:
            errors.append({"field": "name", "error": "must not be empty"})

    # --- age ---
    if "age" not in body:
        errors.append({"field": "age", "error": "required"})
    else:
        age = body["age"]
        # ``bool`` is a subclass of ``int``; exclude it explicitly.
        if isinstance(age, bool) or not isinstance(age, int):
            errors.append({"field": "age", "error": "must be an integer"})
        elif age < 0:
            errors.append({"field": "age", "error": "must be >= 0"})

    return errors
