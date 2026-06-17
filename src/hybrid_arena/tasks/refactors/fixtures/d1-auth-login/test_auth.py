"""Tests for ``auth.login``.

Passwords for seeded users: ``"correct-horse-battery-staple"``.
"""

from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth import InvalidCredentials, hash_password, login  # noqa: E402
from users import get_user  # noqa: E402

PASSWORD = "correct-horse-battery-staple"


def test_seeded_users_have_matching_hashes():
    """Sanity: the shipped salt/hash pairs must be what
    ``hash_password`` produces for the documented password. If this
    fails, ``hash_password`` is wrong, not ``login``.
    """
    ada = get_user("ada@example.com")
    assert ada is not None
    assert hash_password(PASSWORD, ada.salt) == ada.pw_hash


def test_login_happy_path_returns_32_char_hex():
    token = login("ada@example.com", PASSWORD)
    assert isinstance(token, str)
    assert len(token) == 32
    assert re.fullmatch(r"[0-9a-f]{32}", token)


def test_login_wrong_password_raises():
    with pytest.raises(InvalidCredentials):
        login("ada@example.com", "hunter2")


def test_login_unknown_email_raises():
    with pytest.raises(InvalidCredentials):
        login("ghost@example.com", PASSWORD)


def test_login_returns_fresh_token_each_call():
    a = login("ada@example.com", PASSWORD)
    b = login("ada@example.com", PASSWORD)
    assert a != b, "token must be freshly minted per login"


def test_login_accepts_second_seeded_user():
    token = login("grace@example.com", PASSWORD)
    assert re.fullmatch(r"[0-9a-f]{32}", token)
