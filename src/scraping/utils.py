from time import sleep 
from src.config import config

from src.utils.logging import get_logger

calls_logger = get_logger('scraper.calls')

def url_to_filename(url: str) -> str:
    return url.lstrip('https://').lstrip('http://').rstrip('/').replace('/', '_').replace('.', '-')
    

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
            calls_logger.warning(f'Caught an error on try {retries+1}: {e}')
            last_error = e
            retries += 1

            backoff_time = delay * backoff_rate**retries
            calls_logger.info(f'Retrying with exponential backoff time {backoff_time} sec.')
            sleep(backoff_time)
    
    return { 'result': None, 'retries': retries, 'last_error': last_error, 'status': 'FAIL' }
