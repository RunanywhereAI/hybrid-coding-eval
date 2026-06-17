"""De-duplicate a CSV on its first column, preserving the header and
the first occurrence of each key. Reads stdin, writes stdout.
"""

from __future__ import annotations

import csv
import sys


def main() -> int:
    reader = csv.reader(sys.stdin)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    try:
        header = next(reader)
    except StopIteration:
        return 0
    writer.writerow(header)

    seen: set[str] = set()
    for row in reader:
        if not row:
            continue
        key = row[0]
        if key in seen:
            continue
        seen.add(key)
        writer.writerow(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
