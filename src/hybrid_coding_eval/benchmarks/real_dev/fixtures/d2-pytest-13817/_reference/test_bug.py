"""Regression test for https://github.com/pytest-dev/pytest/issues/13817.

Calling ``parser.addoption("shuffle")`` (without the leading ``--``) from
``conftest.py`` raises ``ArgumentError`` inside ``Argument.__init__``. That
in turn tries to format ``self`` via ``__repr__`` for the error message,
but ``__repr__`` accesses ``self.dest`` which goes through ``self._action``
-- which isn't initialised yet at that point -- and crashes with a secondary
``AttributeError`` that masks the original error.

Fixed by guarding ``Argument.__repr__`` so it returns a placeholder when
``_action`` has not yet been set.
"""

from __future__ import annotations

from _pytest.config.argparsing import Argument


def test_argument_repr_uninitialized():
    """``__repr__`` must not crash if ``_action`` has not been set yet.

    Before the fix this raised ``AttributeError: 'Argument' object has no
    attribute 'dest'`` (which itself cascades into the stacktrace shown in
    issue #13817).
    """
    arg = Argument.__new__(Argument)
    result = repr(arg)
    assert result == "Argument(<uninitialized>)"
