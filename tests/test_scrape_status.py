from datetime import datetime, timezone

from scripts.scrape_status import HEADER, pages_from_log, render


def test_pages_parsed_from_scraper_log():
    log = "(2026.10.18 09:42:29) scraper.core\t INFO: Loaded sitemaps with 261 pages\n"
    assert pages_from_log(log) == 261
    assert pages_from_log("no such line") is None


def test_render_prepends_newest_row_and_keeps_history():
    first = render("", datetime(2026, 10, 11, 11, 25, tzinfo=timezone.utc), 263,
                   {"de": 233, "en": 149, "embax_en": 13})
    assert first.startswith(HEADER)
    assert "| 2026-10-11 11:25 | 2026-W41 | 263 | 233 | 149 | 13 |" in first

    second = render(first, datetime(2026, 10, 18, 9, 39, tzinfo=timezone.utc), 261,
                    {"de": 233, "en": 149, "embax_en": 13})
    rows = [l for l in second.splitlines() if l.startswith("| 2026-")]
    assert rows[0].startswith("| 2026-10-18 09:39 | 2026-W42 | 261 ")
    assert rows[1].startswith("| 2026-10-11 11:25 | 2026-W41 | 263 ")
    assert second.count(HEADER) == 1


def test_missing_values_render_as_na():
    out = render("", datetime(2026, 1, 1, tzinfo=timezone.utc), None, {})
    assert "| n/a | n/a | n/a | n/a |" in out
