"""Regression test for https://github.com/pallets/werkzeug/issues/3127.

When a ``WWWAuthenticate`` challenge has no parameters (e.g. bare
``Bearer`` auth scheme), ``to_header()`` used to leave a trailing whitespace
after the scheme name: ``"Bearer "`` instead of ``"Bearer"``.

Some downstream HTTP libraries (e.g. ``h11``) reject the resulting header as
malformed:

    h11._util.LocalProtocolError: Illegal header value b'Bearer '

Fixed by short-circuiting ``to_header()`` to return just the auth-scheme
(title-cased) when there are no parameters.
"""

from __future__ import annotations

from werkzeug.datastructures import WWWAuthenticate


def test_bearer_without_parameters_has_no_trailing_whitespace():
    """Parameter-less ``Bearer`` challenges must not render as ``'Bearer '``."""
    wa = WWWAuthenticate("bearer")
    header = wa.to_header()
    assert header == "Bearer"
    assert not header.endswith(" ")


def test_basic_with_parameters_still_renders_normally():
    """Existing behaviour for parametrised challenges must be preserved."""
    wa = WWWAuthenticate("basic", {"realm": "Foo Bar"})
    assert wa.to_header() == 'Basic realm="Foo Bar"'
