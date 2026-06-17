"""Reference ``login`` implementation.

Constant-time compare, uniform failure path so unknown-user vs
wrong-password aren't distinguishable, fresh 32-char hex token per
successful login.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from users import get_user

PBKDF2_ITERATIONS = 100_000


class InvalidCredentials(Exception):
    pass


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )


def login(email: str, password: str) -> str:
    user = get_user(email)
    if user is None:
        # Still hash something so timing roughly matches the happy path.
        hash_password(password, b"\x00" * 16)
        raise InvalidCredentials("invalid credentials")

    candidate = hash_password(password, user.salt)
    if not hmac.compare_digest(candidate, user.pw_hash):
        raise InvalidCredentials("invalid credentials")

    return secrets.token_hex(16)
