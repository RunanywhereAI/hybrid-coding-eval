"""Example consumer — pulls from every slice of ``utils``. Must keep
working after the refactor (updated imports allowed).
"""

from __future__ import annotations

from utils import (
    configure_logging,
    dump_jsonl,
    ensure_dir,
    get_logger,
    http_get_with_retry,
    iter_files,
    render,
    slugify,
)


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
