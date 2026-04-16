import re
from urllib.parse import urlsplit, urlparse
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
        parsed = urlparse(url)

        # Build base from netloc + path
        filename = f"{parsed.netloc}{parsed.path}"

        # Remove leading/trailing slashes
        filename = filename.strip('/')

        # Replace separators
        filename = filename.replace('/', '_').replace('.', '-')

        # Remove all problematic characters
        filename = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)

        return filename
    

    def filter_discovered_urls(self, discovered_urls, visited_urls, target_domain) -> list:
        filtered_urls = set()
        
        for url in discovered_urls: 
            if any([self.is_url_blacklisted(url), url in visited_urls, urlsplit(url).netloc != target_domain]): 
                continue
            filtered_urls.add(url)
        
        return filtered_urls
