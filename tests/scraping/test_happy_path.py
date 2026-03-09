import pytest, os

from src.utils.logging import init_logging

from src.scraping.scraper import Scraper
from src.scraping.utils import url_to_filename
from src.config import config

class TestHappyPath:

    def test_happy_path(self):
        init_logging()

        target_url = config.get('SCRAPING_TARGET_URLS')[0]
        url_filename = url_to_filename(target_url)
        scraper = Scraper()
        
        results = scraper.scrape(target_url)
        assert len(results) > 0
        
        logs_file_path = os.path.join(config.paths.LOGS, 'scraping.log')
        raw_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
        extracted_text_file_path = os.path.join(config.paths.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')
        
        # Test that the logs are being written
        assert os.path.exists(logs_file_path)
        with open(logs_file_path, 'r') as f:
            assert len(f.read()) > 0

        # Test whether the raw HTML was extracted and saved
        assert os.path.exists(raw_html_file_path)
        with open(raw_html_file_path, 'r') as f:
            assert len(f.read()) > 0
            
        # Test whether the text was extracted and saved
        assert os.path.exists(extracted_text_file_path)
        with open(raw_html_file_path, 'r') as f:
            assert len(f.read()) > 0



if __name__ == '__main__':
    pytest.main([__file__, '-v'])
