"""Authentication helpers — ``login`` is TO BE IMPLEMENTED.

Use stdlib only:

- ``hashlib.pbkdf2_hmac("sha256", password, salt, 100_000)`` produces
  the 32-byte hash that matches what ``users.py`` ships.
- ``hmac.compare_digest`` for constant-time comparison.
- ``secrets.token_hex(16)`` for a 32-char session token.
"""

from __future__ import annotations

import hashlib

from users import get_user


PBKDF2_ITERATIONS = 100_000


class InvalidCredentials(Exception):
    """Raised when ``login`` rejects the caller."""


def hash_password(password: str, salt: bytes) -> bytes:
    """Return the 32-byte PBKDF2 hash for ``(password, salt)``."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )


def login(email: str, password: str) -> str:
    """Return a 32-char hex session token on success.

    Raise ``InvalidCredentials`` when the email is unknown OR the
    password doesn't match. The two cases MUST be indistinguishable
    to the caller (same exception, same message).

    The comparison must be constant-time to avoid timing attacks.
    """
    # TODO: look the user up by email (use ``get_user``), verify the
    # password with ``hmac.compare_digest``, and return
    # ``secrets.token_hex(16)`` on success.
    raise NotImplementedError
