import requests, json, os, re, difflib
from collections import defaultdict
from time import sleep 
from urllib.robotparser import RobotFileParser
from urllib.error import URLError
from fake_useragent import UserAgent

from ..config import config
from ..const.page_priority import *
from ..const.page_blacklist import PAGE_BLACKLIST
from ..utils.logging import get_logger

logger = get_logger('scraper.utils')
ua = UserAgent()


def url_to_filename(url: str) -> str:
    return url.lstrip('https://').lstrip('http://').rstrip('/').replace('/', '_').replace('.', '-')


def _fuzzy_match(word, keyword, threshold=0.8):
    """
    Check if word fuzzy matches keyword using difflib ratio.
    """
    return difflib.SequenceMatcher(None, word.lower(), keyword.lower()).ratio() >= threshold


def is_url_blacklisted(url: str) -> bool:
    url_lower = url.lower()
    path = url_lower.split('://', 1)[-1].split('/', 1)[-1] 
    
    for forbidden in PAGE_BLACKLIST:
        if forbidden in path:
            return True
            
    return False


def detect_topic_and_priority(text: str, language: str):
    text_lower = text.lower()
    words = re.findall(r'\w+', text_lower)
    
    for word in words:
        for kw in PAGE_PRIORITY_KEYWORDS_HIGH[language]:
            if _fuzzy_match(word, kw):
                return kw, 'high'
        for kw in PAGE_PRIORITY_KEYWORDS_MEDIUM[language]:
            if _fuzzy_match(word, kw):
                return kw, 'medium'
        for kw in PAGE_PRIORITY_KEYWORDS_LOW[language]:
            if _fuzzy_match(word, kw):
                return kw, 'low'

    return 'low', 'none'


def load_set_dict(
    path: str,
    dict_name: str, 
    refresh_entry: str = '', 
) -> dict:
    url_dict = defaultdict(set)
    urls_json_path = os.path.join(path, f'{dict_name}.json') 
    if os.path.exists(urls_json_path) and refresh_entry != 'all':
        try:
            with open(urls_json_path, 'r') as f:
                url_dict = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load URL dictionary '{dict_name}': {e}")
    
    if refresh_entry in url_dict.keys():
        if isinstance(url_dict[refresh_entry], list):
            url_dict[refresh_entry].clear() 

    for key in url_dict.keys():
        if isinstance(url_dict[key], list):
            url_dict[key] = set(url_dict[key])

    return url_dict


def write_set_dict(
    path: str, 
    dict_name: str, 
    urls_dict: dict,
):
    urls_json_path = os.path.join(path, f'{dict_name}.json')
    
    for key in urls_dict.keys():
        if isinstance(urls_dict[key], set):
            urls_dict[key] = list(urls_dict[key])
    
    try:
        with open(urls_json_path, 'w') as f:
            json.dump(urls_dict, f, indent=4, default=str)
    except Exception as e:
        logger.error(f"Failed to save ULR dictionary '{dict_name}': {e}")


def fetch_url(url: str) -> dict:
    try:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=15,
            headers={"User-Agent": ua.chrome}
        )
        if response.status_code >= 400:
            logger.warning(f"HTTP {response.status_code} for {url}")
            raise Exception() 

        return {"text": response.text, "final_url": response.url}
    except Exception as e:
        logger.exception(f"Fetch failed: {url}")
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
    except Exception as e:
        raise e


def parse_robots(base_url: str) -> RobotFileParser | None:
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
        logger.error(f"Failed to fetch the 'robots.txt': {response['last_error']}") 
        return None 

    return rp

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
