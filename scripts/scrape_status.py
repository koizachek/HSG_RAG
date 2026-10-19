"""Record the outcome of a weekly scrape in docs/scrape-status.md.

The scrape workflow writes nothing into the repository, so it was invisible in
the commit history. This script appends one row per run (date, sitemap pages,
Weaviate object counts) to a Markdown table that the workflow commits.

Usage (CI):
    python scripts/scrape_status.py --log scrape.log --out docs/scrape-status.md

Reads WEAVIATE_CLUSTER_URL / WEAVIATE_API_KEY from the environment.
"""
from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path

HEADER = (
    "# Scrape status\n\n"
    "Written automatically by `.github/workflows/scrape.yml` after every "
    "successful weekly scrape of emba.unisg.ch and embax.ch. Newest run first. "
    "Object counts are the Weaviate collection totals right after the import.\n\n"
    "| Run (UTC) | Week | Sitemap pages | DE objects | EN objects | embax.ch (EN) |\n"
    "|---|---|---|---|---|---|\n"
)
ROW_RE = re.compile(r"^\| \d{4}-\d{2}-\d{2} ")


def pages_from_log(text: str) -> int | None:
    m = re.search(r"Loaded sitemaps with (\d+) pages", text)
    return int(m.group(1)) if m else None


def weaviate_counts() -> dict[str, int]:
    import weaviate
    from weaviate.classes.init import Auth
    from weaviate.classes.query import Filter

    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=os.environ["WEAVIATE_CLUSTER_URL"],
        auth_credentials=Auth.api_key(os.environ["WEAVIATE_API_KEY"]),
    )
    try:
        counts = {}
        for key, name in (("de", "hsg_rag_content_de"), ("en", "hsg_rag_content_en")):
            coll = client.collections.get(name)
            counts[key] = coll.aggregate.over_all(total_count=True).total_count or 0
        en = client.collections.get("hsg_rag_content_en")
        counts["embax_en"] = (
            en.aggregate.over_all(
                filters=Filter.by_property("source").like("*embax.ch*"), total_count=True
            ).total_count
            or 0
        )
        return counts
    finally:
        client.close()


def render(existing: str, run_at: datetime, pages: int | None, counts: dict[str, int]) -> str:
    rows = [line for line in existing.splitlines() if ROW_RE.match(line)]
    new_row = (
        f"| {run_at:%Y-%m-%d %H:%M} | {run_at:%G-W%V} | {pages if pages is not None else 'n/a'} "
        f"| {counts.get('de', 'n/a')} | {counts.get('en', 'n/a')} | {counts.get('embax_en', 'n/a')} |"
    )
    return HEADER + "\n".join([new_row, *rows]) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="captured scraper stdout/stderr")
    ap.add_argument("--out", default="docs/scrape-status.md")
    ap.add_argument("--skip-weaviate", action="store_true", help="tests only")
    args = ap.parse_args()

    pages = pages_from_log(Path(args.log).read_text(errors="replace"))
    counts = {} if args.skip_weaviate else weaviate_counts()
    out = Path(args.out)
    existing = out.read_text() if out.exists() else ""
    out.write_text(render(existing, datetime.now(timezone.utc), pages, counts))
    print(f"scrape status: pages={pages} counts={counts} -> {out}")


if __name__ == "__main__":
    main()
