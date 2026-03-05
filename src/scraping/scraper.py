import os

from src.scraping.utils import *
from src.scraping.html_processor import HTMLProcessor
from src.pipeline.utilclasses import ProcessingResult
from src.utils.logging import get_logger
from src.config import config

logger = get_logger('scraper.core')

class Scraper:
    def __init__(self) -> None:
        self._processor    = HTMLProcessor()
                
        os.makedirs(config.paths.URLS_OUTPUT,           exist_ok=True)
        os.makedirs(config.paths.RAW_HTML_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.EXTRACTED_TEXT_OUTPUT, exist_ok=True)

        logger.info(f'Successfully initialized the scraper')
    
    def scrape(self, target_url: str) -> list[ProcessingResult]:
        results = []

        if not target_url:
            logger.warning('The target URL string is empty!')
            return results
       
        # Test whether the target URL is even accessible before initializing the scraping procedure
        response = call_with_exponential_backoff(fetch_url, args=(target_url,))
        if response['status'] == 'FAIL':
            logger.error(f"Unaccessible target URL '{target_url}': {response['last_error']}")
            return results
        if not response['result']:
            logger.warning(f"Unnaccessible target URL '{target_url}': Recieved client/server error!")
            return results

        logger.info(f"Starting the scraping process for the target URL '{target_url}'...")
        rp = parse_robots(target_url)
        
        if not rp:
            logger.warning(
                f"Could not fetch the 'robots.txt' file for the target URL '{target_url}'! " +
                 "(Are you sure the scraping begins from root?)"
            )
            return results
        
        logger.info(f"Parsed the 'robots.txt' file for target URL '{target_url}'")

        crawl_delay = rp.crawl_delay('scraper')
        
        urls = [target_url] 
        while urls:
            url = urls.pop()
            if not url: continue
            
            logger.info(f"Fetching URL '{url}'...")
            response = call_with_exponential_backoff(fetch_url, args=(url,), delay=crawl_delay)
            if response['status'] == 'FAIL':
                logger.warning("Failed to fetch URL '{url}': {response['last_error']}")
                continue
            if not response['result']:
                logger.warning("Cannot fetch '{url}'!")
                continue
            
            raw_html = response['result']
            
            url_filename = url_to_filename(url) 
            raw_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
            with open(raw_html_file_path, 'w') as f:
                f.write(raw_html)
                logger.info(f"Saved fetched HTML under '{raw_html_file_path}'")

            logger.info(f"Processing URL '{url}'...")
            processed = self._processor.process(url, raw_html)
            
            if not processed['result'].chunks:
                logger.warning(f"Failed to process URL '{url}'")
                continue
            
            extracted_text_file_path = os.path.join(config.paths.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')
            with open(extracted_text_file_path, 'w') as f:
                f.write(processed['text'])
                logger.info(f"Saved extracted text under '{extracted_text_file_path}'")

            results.append(processed['result'])
        
        return results
