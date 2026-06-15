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

        # Guard against junk/tracking URLs without dropping legitimate content
        # pages. A plain length cap (previously: len(path) > 35) silently
        # skipped real pages such as /admissions/ready-to-relearn-the-future/
        # (39 chars). Use structural signals instead:
        if '?' in path or '&' in path or '=' in path:
            return True  # query strings: filters, tracking, form states
        if path.count('/') > 4:
            return True  # deeper than any real content page on the targets
        return len(path) > 100  # extreme guard for runaway slugs
    

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
