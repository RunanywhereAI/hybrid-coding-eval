"""Regression test for https://github.com/pallets/click/issues/3298.

When ``show_default=True`` and the default value has an ``__eq__`` that
raises or misbehaves on string operands (e.g. ``semver.Version``), Click
previously crashed while rendering the help text because it compared the
default against ``""`` unconditionally.

The fix is to guard the empty-string comparison with an ``isinstance``
check so only string defaults take that branch.
"""

from __future__ import annotations

import click


class _StrictEq:
    """Object whose ``__eq__`` raises on string comparison (like ``semver.Version``)."""

    def __eq__(self, other):
        if isinstance(other, str):
            raise ValueError("cannot compare to string")
        return NotImplemented

    def __str__(self):
        return "strict"


def test_show_default_with_empty_string():
    """When show_default is True and default is an empty string."""
    opt = click.Option(["--limit"], default="", show_default=True)
    ctx = click.Context(click.Command("cli"))
    message = opt.get_help_record(ctx)[1]
    assert '[default: ""]' in message


def test_show_default_with_non_string_comparable_object():
    """The empty-string check must not break on objects whose __eq__ raises
    for string operands."""
    opt = click.Option(["--limit"], default=_StrictEq(), show_default=True)
    ctx = click.Context(click.Command("cli"))
    message = opt.get_help_record(ctx)[1]
    assert "[default: strict]" in message
