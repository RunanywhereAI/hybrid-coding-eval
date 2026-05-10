"""Regression test for https://github.com/python-jsonschema/jsonschema/issues/1124.

Version 4.18.1 regressed when a ``RefResolver`` was used against a schema that
has no ``$id``: the resolver would be pushed an empty-bytes scope and later
crash trying to resolve a ``$ref`` with a ``KeyError: b''`` followed by
``AttributeError: 'bytes' object has no attribute 'timeout'``.

Fixed by guarding the ``push_scope`` call in ``create()`` so that it only
pushes when ``id_of(self.schema)`` is not ``None``.
"""

from __future__ import annotations

from jsonschema import validators


def test_refresolver_with_pointer_in_schema_with_no_id():
    """Schema has no ``$id`` but does use ``$ref`` to local definitions.

    Reproduces https://github.com/python-jsonschema/jsonschema/issues/1124#issuecomment-1632574249.
    """
    schema = {
        "properties": {"x": {"$ref": "#/definitions/x"}},
        "definitions": {"x": {"type": "integer"}},
    }

    validator = validators.Draft202012Validator(
        schema,
        resolver=validators._RefResolver("", schema),
    )
    assert validator.is_valid({"x": "y"}) is False
    assert validator.is_valid({"x": 37}) is True
