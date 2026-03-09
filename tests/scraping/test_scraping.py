import pytest, os

from src.scraping.utils import url_to_filename
from src.scraping.scraper import Scraper
from src.utils.logging import init_logging 
from src.config import config

init_logging()

class TestScrapingErrors:
    
    def _invalid_url_scrape_test(self, invalid_url):
        url_filename = url_to_filename(invalid_url)
        url_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
        url_txt_file_path  = os.path.join(config.paths.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')

        scraper = Scraper()

        result = scraper.scrape(invalid_url)
        
        assert not result
        assert not os.path.exists(url_html_file_path)
        assert not os.path.exists(url_txt_file_path)


    def test_invalid_target_url(self, caplog):
        invalid_url = 'https://gugel.pl'
        self._invalid_url_scrape_test(invalid_url)
        
        assert f"Unaccessible target URL '{invalid_url}'" in caplog.text
        

    def test_target_url_with_no_robots(self, caplog):
        invalid_url = 'https://emba.unisg.ch/programm/emba'
        self._invalid_url_scrape_test(invalid_url)

        assert f"Could not fetch the 'robots.txt' file for the target URL '{invalid_url}'!" in caplog.text 

if __name__ == "__main__":
    pytest.main([__file__, '-v']) 
