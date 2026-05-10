"""Schema validation — TO BE IMPLEMENTED.

Implement ``validate_user`` so ``POST /users`` rejects malformed
bodies with HTTP 422 and a structured error per the prompt.
"""

from __future__ import annotations

from typing import Any


def validate_user(body: Any) -> list[dict[str, str]]:
    """Validate a user-creation body.

    Returns a list of error dicts. Each dict MUST contain:

    - ``"field"``: the name of the offending field (e.g. ``"name"``).
    - ``"error"``: a short human-readable message.

    Return ``[]`` for a valid body.

    A body is valid iff:

    - it is a dict;
    - ``name`` is present AND a non-empty string;
    - ``age`` is present AND an int AND ``>= 0`` (booleans don't count
      as ints here — ``True`` is not a valid age).

    Unknown extra keys are allowed.
    """
    raise NotImplementedError
