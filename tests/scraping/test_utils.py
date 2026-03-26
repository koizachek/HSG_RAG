from datetime import datetime
import pytest

from src.scraping.utils import *

class TestScrapingUtils:

    def test_url_fetching(self):
        url = 'https://embax.ch/'
        
        fetch_result = fetch_url(url)
        assert fetch_result
        assert len(fetch_result['text']) > 100
        assert fetch_result['final_url'] == url
        assert isinstance(fetch_result['last_modified'], datetime) 


if __name__ == "__main__":
    pytest.main([__file__, '-v', '-s']) 
