from urllib.parse import urlsplit
from ..const.page_blacklist import *

class UrlNormalizer:
    @staticmethod
    def is_url_blacklisted(url: str) -> bool:
        url_lower = url.lower()
        path = url_lower.split('://', 1)[-1].split('/', 1)[-1] 
        
        for forbidden in PAGE_BLACKLIST:
            if forbidden in path:
                return True
                
        return False
    

    @staticmethod
    def url_to_filename(url: str) -> str:
        return url.lstrip('https://').lstrip('http://').rstrip('/').replace('/', '_').replace('.', '-')
    

    def filter_discovered_urls(self, discovered_urls, visited_urls, target_domain) -> list:
        filtered_urls = set()
        
        for url in discovered_urls: 
            if any([self.is_url_blacklisted(url), url in visited_urls, urlsplit(url).netloc != target_domain]): 
                continue
            filtered_urls.add(url)
        
        return filtered_urls
