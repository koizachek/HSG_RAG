from time import sleep

from .logging import get_logger 
from ..config import config

logger = get_logger("utils.backoff")

def call_with_exponential_backoff(
    func, 
    args: tuple = (), 
    delay: float | None = None, 
    backoff_rate: float | None = None,
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
