import hashlib
import json
import requests, difflib, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from collections import defaultdict
from time import sleep 
from urllib.robotparser import RobotFileParser
from urllib.error import URLError
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

from src.scraping.types import FetchResult

from ..config import config
from ..const.page_priority import *
from ..utils.logging import get_logger

logger = get_logger('scraper.utils')
ua = UserAgent()

@lru_cache
def _fuzzy_match(word, keyword, threshold=0.8):
    """
    Check if word fuzzy matches keyword using difflib ratio.
    """
    return difflib.SequenceMatcher(None, word.lower(), keyword.lower()).ratio() >= threshold


def detect_page_topic_and_priority(text: str) -> dict[str, str]:
    result = {
        'priority': 'low',
        'topic': 'none',
    }

    if not text: return result

    text_lower = text.lower()
    words = text_lower.split()
    topic_counter = { prio: defaultdict(int) for prio in PAGE_PRIORITY_KEYWORDS.keys() }
    prio_counter  = { prio: 0 for prio in PAGE_PRIORITY_KEYWORDS.keys() } 

    for word in words:
        for prio, kws in PAGE_PRIORITY_KEYWORDS.items():
            for kw in kws:
                if _fuzzy_match(word, kw):
                    topic_counter[prio][kw] += 1
            prio_counter[prio] += sum(topic_counter[prio].values())
    
    if max(prio_counter.values()) == 0:
        return result

    top_prio  = max(prio_counter.keys(), key=lambda k: prio_counter[k])
    top_topic = max(topic_counter[top_prio].keys(), key=lambda k: topic_counter[top_prio][k])

    result['priority'] = top_prio 
    result['topic']    = top_topic
    
    return result 


def detect_chunk_topic(text: str) -> str:
    if not text: return 'none'

    text_lower = text.lower()
    words = text_lower.split() 
    topic_counter = { topic: 0 for topic in CHUNK_TOPIC_KEYWORDS.keys() }
    
    for word in words:
        for topic, kws in CHUNK_TOPIC_KEYWORDS.items():
            topic_counter[topic] += len(list(filter(lambda kw: _fuzzy_match(word, kw), kws)))
     
    if max(topic_counter.values()) == 0:
        return 'none'

    top_topic = max(topic_counter.keys(), key=lambda k: topic_counter[k])
    return top_topic 


def hash_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text()
    return hashlib.sha256(text.encode()).hexdigest()


def parse_isoformat(data: str) -> datetime.datetime:
    if not data:
        return None

    try:
        return parsedate_to_datetime(data)
    except (TypeError, ValueError):
        pass

    try:
        return datetime.datetime.fromisoformat(data)
    except ValueError:
        pass

    return None


def extract_last_modified(response, html) -> datetime.datetime | None: 
    last_modified = response.headers.get("Last-Modified", None)
    
    soup = BeautifulSoup(html, "html.parser")
    if not last_modified:
        for key in [ ("name", "last-modified"), ("property", "article:modified_time")]: 
            tag = soup.find("meta", {key[0]: key[1]})
            if tag:
                last_modified = tag.get("content")
                break

    if not last_modified:
        scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in scripts:
            try:
                data = json.loads(script.string)
            except:
                continue

            graph = data.get("@graph") if isinstance(data, dict) else None

            if graph:
                for item in graph:
                    if item.get("@type") in ["WebPage", "Article"]:
                        last_modified = item.get("dateModified")
                        if last_modified:
                            break
        
    return parse_isoformat(last_modified)


def fetch_head(url: str, etag: str | None = None) -> FetchResult:
    try:
        headers = {"User-Agent": ua.chrome}
        if etag:
            headers["If-None-Match"] = etag

        response = requests.head(
            url,
            allow_redirects=True,
            timeout=15,
            headers=headers
        )
        if response.status_code == 304:
            return FetchResult(not_modified=True)

        if response.status_code >= 400:
            logger.warning(f"HTTP {response.status_code} for URL '{url}'")
            raise Exception() 

        return FetchResult(
            final_url     = response.url,
            last_modified = response.headers.get('Last-Modified'), 
            etag          = response.headers.get('ETag')
        )
    except Exception as e:
        logger.exception(f"Head fetch failed: {url}")
        raise e 


def fetch_url(url: str, etag: str | None = None) -> dict:
    try:
        headers = {"User-Agent": ua.chrome}
        if etag:
            headers["If-None-Match"] = etag

        response = requests.get(
            url,
            allow_redirects=True,
            timeout=15,
            headers=headers
        )
        if response.status_code == 304:
            return FetchResult(not_modified=True)

        if response.status_code >= 400:
            logger.warning(f"HTTP {response.status_code} for URL '{url}'")
            raise Exception() 
       
        html = response.text  
        etag = response.headers.get("ETag")
        last_modified = extract_last_modified(response, html)
        page_hash = hash_html(html)

        return FetchResult(
            text          = html, 
            final_url     = response.url,
            page_hash     = page_hash,
            last_modified = last_modified,
            etag          = etag,
        )
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
