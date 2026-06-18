import pytest, os
from datetime import datetime, timedelta
from types import SimpleNamespace

from src.scraping.types import FetchResult, ScrapingStatus, UrlTimestamps
from src.scraping.url_normalizer import UrlNormalizer
from src.scraping.scraper import Scraper
from src.utils.logging import init_logging
from src.config import config

init_logging()


class TestScrapingErrors:

    def _invalid_url_scrape_test(self, invalid_url):
        url_filename = UrlNormalizer().url_to_filename(invalid_url)
        url_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
        url_txt_file_path = os.path.join(config.paths.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')

        scraper = Scraper()

        result = scraper.scrape_target(invalid_url)

        assert not result
        assert not os.path.exists(url_html_file_path)
        assert not os.path.exists(url_txt_file_path)

    @pytest.mark.network
    @pytest.mark.integration
    def test_invalid_target_url(self, caplog):
        invalid_url = 'https://gugel.pl'
        self._invalid_url_scrape_test(invalid_url)

        assert f"Unaccessible target URL '{invalid_url}'" in caplog.text

    @pytest.mark.network
    @pytest.mark.integration
    def test_target_url_with_no_robots(self, caplog):
        invalid_url = 'https://emba.unisg.ch/programm/emba'
        self._invalid_url_scrape_test(invalid_url)

        assert f"Could not fetch the 'robots.txt' file for the target URL '{invalid_url}'!" in caplog.text

    def test_last_scraped_priority(self, caplog):
        scraper = Scraper()
        scraper._url_priorities = {"high": ["h1", "h2", "h3"], "medium": ["m1", "m2", "m3"], "low": ["l1", "l2", "l3"]}
        date = datetime.now()
        scraper._url_timestamps = {
            "h1": UrlTimestamps(last_scraped=date - timedelta(days=1)),
            "h2": UrlTimestamps(last_scraped=date - timedelta(days=2)),
            "h3": UrlTimestamps(last_scraped=date - timedelta(hours=23)),
            "m1": UrlTimestamps(last_scraped=date - timedelta(days=1)),
            "m2": UrlTimestamps(last_scraped=date - timedelta(days=6)),
            "m3": UrlTimestamps(last_scraped=date - timedelta(days=7)),
            "l1": UrlTimestamps(last_scraped=date - timedelta(days=7)),
            "l2": UrlTimestamps(last_scraped=date - timedelta(days=29)),
            "l3": UrlTimestamps(last_scraped=date - timedelta(days=30)),
        }
        expected = {
            "h1": True,
            "h2": True,
            "h3": False,
            "m1": False,
            "m2": False,
            "m3": True,
            "l1": False,
            "l2": False,
            "l3": True,
        }

        for url in scraper._url_timestamps:
            assert scraper._is_url_prioritized(url) == expected[url]

    def test_head_timeout_falls_back_to_get(self, tmp_path, monkeypatch):
        url = "https://embax.ch/contact/"
        get_calls = []
        scraper = Scraper.__new__(Scraper)
        scraper._scrape_all = True
        scraper._url_timestamps = {}
        scraper._url_priorities = {}
        scraper._normalizer = SimpleNamespace(
            is_url_blacklisted=lambda _: False,
            url_to_filename=lambda _: "embax-contact",
        )
        scraper._content_cleaner = SimpleNamespace(
            clean_mobile_content=lambda html: html,
            extract_urls=lambda document: [],
            collect_repetitive_content=lambda document: None,
        )
        scraper._processor = SimpleNamespace(
            process=lambda final_url, html: SimpleNamespace(name=final_url),
            convert_to_txt=lambda document: "contact page",
        )

        def fail_head(*_):
            raise TimeoutError("HEAD timed out")

        def fetch_get(request_url, etag):
            get_calls.append((request_url, etag))
            return FetchResult(
                final_url=request_url,
                last_modified=None,
                etag=None,
                text="<html><body>Contact</body></html>",
                page_hash="hash",
            )

        def no_wait_backoff(func, args=(), **_):
            return {
                "result": func(*args),
                "retries": 0,
                "last_error": None,
                "status": "OK",
            }

        monkeypatch.setattr("src.scraping.scraper.fetch_head", fail_head)
        monkeypatch.setattr("src.scraping.scraper.fetch_url", fetch_get)
        monkeypatch.setattr(
            "src.scraping.scraper.call_with_exponential_backoff",
            no_wait_backoff,
        )
        monkeypatch.setattr(config.paths, "RAW_HTML_OUTPUT", str(tmp_path))
        monkeypatch.setattr(config.paths, "RAW_TEXT_OUTPUT", str(tmp_path))

        result = scraper._scrape_page(
            url=url,
            crawl_delay=0,
            visited_urls=set(),
        )

        assert result.status == ScrapingStatus.OK
        assert result.final_url == url
        assert get_calls == [(url, None)]


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
