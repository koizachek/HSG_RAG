import pytest, os
from datetime import datetime, timedelta

from src.scraping.types import UrlTimestamps
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


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
