"""Redact credential-like top-level string values in a JSON document.

Reads JSON from stdin. Any top-level key whose NAME contains one of
``KEY``, ``TOKEN``, ``SECRET``, or ``PASSWORD`` (case-insensitive), and
whose value is a string, is replaced with ``<REDACTED>``. Nested
structures are preserved verbatim. Writes pretty-printed JSON
(``indent=2``) to stdout, with a trailing newline.
"""

from __future__ import annotations

import json
import re
import sys

_NEEDLE = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)


def main() -> int:
    data = json.load(sys.stdin)
    if isinstance(data, dict):
        for key, value in list(data.items()):
            if isinstance(value, str) and _NEEDLE.search(key):
                data[key] = "<REDACTED>"
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
