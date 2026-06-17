"""JSON (de)serialisation helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def dumps_pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)


def load_jsonl(path: str | os.PathLike) -> list[Any]:
    out: list[Any] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def dump_jsonl(path: str | os.PathLike, rows: list[Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str))
            fh.write("\n")
