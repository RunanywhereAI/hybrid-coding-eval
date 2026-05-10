"""Glue: attach the retry policy to ``client.fetch_json``.

The model must edit this file to wire the decorator onto ``fetch_json``.
Tests re-import ``client.fetch_json`` to exercise the decorated form.
"""

from __future__ import annotations

import client
from retry import retry  # noqa: F401 - used once the model wires it up.

# TODO: wrap ``client.fetch_json`` with ``retry(...)`` per the spec.
# The tests expect the wrapped function to live at ``client.fetch_json``.
