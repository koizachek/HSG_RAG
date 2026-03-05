import requests, os, sys, logging
from urllib.robotparser import RobotFileParser
from urllib.error import URLError

from src.scraping.utils import url_to_filename, call_with_exponential_backoff
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
    

    def _robots_exist(self, robots_url) -> bool:
        try:
            logger.info(f"Checking if 'robots.txt' accessible on path '{robots_url}'...")
            response = requests.head(robots_url, allow_redirects=True, timeout=config.scraping.TIMEOUT)
            if response.status_code not in [200, 404]:
                logger.error("Cannot access the 'robots.txt' - recieved status code {response.status_code}!")
                return False
            return True
        except requests.RequestException as e:
            raise requests.RequestException(f"An error occured while requesting the URL '{robots_url}': {e}")
        except _ as e:
            raise e


    def _parse_robots(self, base_url: str) -> RobotFileParser:
        robots_url = f'{base_url.rstrip('/')}/robots.txt'
 
        # Check whether the robots.txt file is accessible from this url 
        response = call_with_exponential_backoff(self._robots_exist, args=(robots_url,)) 
        if not response['result']: return None 
        
        logger.info(f"File 'robots.txt' found for the target url '{base_url}'")
        rp = RobotFileParser()
        rp.set_url(robots_url)
        
        # Parse existing robots.txt file into the parser
        def fetch_robots():
            try:
                rp.read()
                return rp 
            except URLError as e:
                raise URLError(f"Failed to fetch the 'robots.txt': {e}")
        
        response = call_with_exponential_backoff(fetch_robots)
        if response['status'] == 'FAIL': 
            logger.error(f"Failed to fetch the 'robots.txt' file after {retries} retries, last error: {last_error}") 
            return None 

        return rp
    

    def scrape(self, target_url: str) -> list[ProcessingResult]:
        results = []

        if not target_url:
            logger.warning('The target URL string is empty!')
            return results
        
        logger.info(f"Starting the scraping process for the target URL '{target_url}'...")
        rp = self._parse_robots(target_url)
        
        if not rp:
            logger.warning(f"File 'robots.txt' is not accessible for target URL '{target_url}'!")
            return results

        logger.info(f"Parsed the 'robots.txt' file for target URL '{target_url}'")

        crawl_delay = rp.crawl_delay('scraper')
        
        def fetch_url(url: str) -> str:
            try:
                response = requests.get(url, allow_redirects=True)
                return response.text
            except Exception as e:
                raise e

        urls = [target_url] 
        while urls:
            url = urls.pop()
            if not url: continue
            
            logger.info(f"Fetching URL '{url}'...")
            response = call_with_exponential_backoff(fetch_url, args=(url,), delay=crawl_delay)
            if response['status'] == 'FAIL':
                logger.warning("Failed to fetch URL '{url}': {response['last_error']}")
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
