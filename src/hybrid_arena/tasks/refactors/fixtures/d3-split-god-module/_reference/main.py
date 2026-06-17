"""Example consumer — updated imports for the split layout."""

from __future__ import annotations

from http_retry import http_get_with_retry
from jsonio import dump_jsonl
from logging_config import configure_logging, get_logger
from paths import ensure_dir, iter_files
from templating import render, slugify


def main() -> None:
    configure_logging("INFO")
    log = get_logger("main")

    out_dir = ensure_dir("./out")
    log.info("writing into %s", out_dir)

    rows = [
        {"title": "Hello world", "slug": slugify("Hello World")},
        {"title": render("User {name}", name="Ada"), "slug": slugify("User Ada")},
    ]
    dump_jsonl(out_dir / "rows.jsonl", rows)

    for p in iter_files(out_dir, suffix=".jsonl"):
        log.info("wrote %s", p)

    try:
        body = http_get_with_retry("http://example.com", retries=1)
        log.info("fetched %d bytes", len(body))
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch failed: %s", exc)


if __name__ == "__main__":
    main()
