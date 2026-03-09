import requests
from time import sleep 
from urllib.robotparser import RobotFileParser
from urllib.error import URLError

from src.config import config
from src.utils.logging import get_logger

logger = get_logger('scraper.utils')

def url_to_filename(url: str) -> str:
    return url.lstrip('https://').lstrip('http://').rstrip('/').replace('/', '_').replace('.', '-')


def fetch_url(url: str) -> str:
    try:
        response = requests.get(url, allow_redirects=True)
        code = response.status_code
        
        if code < 400:
            return response.text 

        logging.warning(f"Catched an error while fetching '{url}': " + 
                        f"{code} {'Client' if code < 500 else 'Server'} Error")
        return ""
    except Exception as e:
        raise e

def _robots_exist(robots_url) -> bool:
    try:
        logger.info(f"Checking if 'robots.txt' accessible on path '{robots_url}'...")
        response = requests.head(robots_url, allow_redirects=True, timeout=config.scraping.TIMEOUT)
        if response.status_code >= 400:
            logger.error("Cannot access the 'robots.txt' - recieved status code {response.status_code}!")
            return False
        return True
    except requests.RequestException as e:
        raise requests.RequestException(f"An error occured while requesting the URL '{robots_url}': {e}")
    except _ as e:
        raise e


def parse_robots(base_url: str) -> RobotFileParser:
    robots_url = f'{base_url.rstrip('/')}/robots.txt'

    # Check whether the robots.txt file is accessible from this url 
    response = call_with_exponential_backoff(_robots_exist, args=(robots_url,)) 
    if not response['result']: return None 
    
    logger.info(f"File 'robots.txt' found for the target url '{base_url}'")
    rp = RobotFileParser()
    rp.set_url(robots_url)
    
    # Parse existing robots.txt file into the parser
    def fetch_robots():
        try:
            rp.read()
        except URLError as e:
            raise URLError(f"Failed to fetch the 'robots.txt': {e}")
    
    response = call_with_exponential_backoff(fetch_robots)
    if response['status'] == 'FAIL': 
        logger.error(f"Failed to fetch the 'robots.txt' file after {retries} retries, last error: {last_error}") 
        return None 

    return rp

def call_with_exponential_backoff(
    func, 
    args: set = set(), 
    delay: int = None, 
    backoff_rate: int = None,
) -> dict:
    retries = 0
    last_error = None

    delay = delay or config.scraping.CRAWL_DELAY 
    backoff_rate = backoff_rate or config.scraping.BACKOFF_RATE

    sleep(delay)
    
    while retries <= config.scraping.MAX_RETRIES:
        try:
            return { 'result': func(*args), 'retries': retries, 'last_error': last_error, 'status': 'OK'}
        except Exception as e:
            logger.warning(f'Caught an error on try {retries+1}: {e}')
            last_error = e
            retries += 1

            backoff_time = delay * backoff_rate**retries
            logger.info(f'Retrying with exponential backoff time {backoff_time} sec.')
            sleep(backoff_time)
    
    return { 'result': None, 'retries': retries, 'last_error': last_error, 'status': 'FAIL' }
