"""Count TODO/FIXME/XXX tokens in .py files under the current directory.

Walks the tree recursively. For each directory that directly contains at
least one .py file, counts tokens (whole-word match for TODO, FIXME, or
XXX) across just the .py files in that directory. Prints one row per
directory: ``<COUNT> <DIR>``, sorted by count desc, directory asc.
"""

from __future__ import annotations

import os
import re
import sys

_PATTERN = re.compile(r"\b(?:TODO|FIXME|XXX)\b")


def main() -> int:
    counts: dict[str, int] = {}
    for dirpath, _dirnames, filenames in os.walk("."):
        py_files = [f for f in filenames if f.endswith(".py")]
        if not py_files:
            continue
        total = 0
        for name in py_files:
            path = os.path.join(dirpath, name)
            with open(path, "r", encoding="utf-8") as fh:
                total += len(_PATTERN.findall(fh.read()))
        counts[dirpath] = total

    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    for d, c in rows:
        sys.stdout.write(f"{c} {d}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
