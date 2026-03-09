import os
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from usp.objects.sitemap import InvalidSitemap
from usp.tree import sitemap_tree_for_homepage

from src.scraping.utils import *
from src.scraping.html_processor  import HTMLProcessor
from src.scraping.content_cleaner import ContentCleaner
from src.pipeline.utilclasses import ProcessingResult
from src.utils.lang import detect_language 
from src.utils.logging import get_logger
from src.config import config

logger = get_logger('scraper.core')

class Scraper:
    def __init__(self) -> None:
        self._processor:       HTMLProcessor  = HTMLProcessor()
        self._content_cleaner: ContentCleaner = ContentCleaner()
        
        os.makedirs(config.paths.URLS_OUTPUT,           exist_ok=True)
        os.makedirs(config.paths.SCRAPING_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.RAW_HTML_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.RAW_TEXT_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.EXTRACTED_TEXT_OUTPUT, exist_ok=True)

        logger.info(f'Successfully initialized the scraper')


    def scrape_target(self, target_url: str) -> list[ProcessingResult]:
        # Step 1: Analyze the target URL for fetching, robots and sitemap
        analyzed_domain = self._analyze_domain(target_url)
        if not analyzed_domain:
            logger.error(f"Failed to scrape target URL '{target_url}'")
            return None
        
        documents        = list()
        discovered_urls  = set() 
        sitemap_urls_dct = load_urls_dictionary('sitemap_urls', target_url)
        
        # Step 2: Validate and scrape URLs listed in the sitemap
        logger.info(f'Starting validation and scraping for sitemap URLs...')
        for url in analyzed_domain['sitemap_urls']:
            if is_url_blacklisted(url):
                logger.info(f"URL '{url}' is blacklisted by scraper, skipping...")
                continue

            scraping_result = self._scrape_page(url, analyzed_domain['delay'])
            if not scraping_result: continue  
            
            documents.append(scraping_result['document'])

            for discovered_url in scraping_result['discovered_urls']: 
                if any([is_url_blacklisted(discovered_url), 
                        urlsplit(discovered_url).netloc != analyzed_domain['target_domain']]): 
                    continue
                discovered_urls.add(discovered_url)

            sitemap_urls_dct[target_url].add(url)

        logger.info(f"Indexed {len(sitemap_urls_dct[target_url])} " +
                    f"out of {len(analyzed_domain['sitemap_urls'])} " +
                    f"sitemap URLs for target URL '{target_url}'")
        
        write_urls_dictionary(sitemap_urls_dct, 'sitemap_urls')
        logger.info(f"Stored sitemap URLs for target URL '{target_url}'")
        
        #Step 3: Analyze discovered URLs and search for the new ones
        discovered_urls = [{'url': url, 'depth': 0} for url in discovered_urls 
                           if url not in sitemap_urls_dct[target_url]]
        discovered_urls_dct = load_urls_dictionary('discovered_urls', target_url)

        logger.info(f"Discovered {len(discovered_urls)} unique URLs while scraping the sitemap URLs")

        if discovered_urls:
            logger.info(f"Starting validation and scraping for discovered URLs...")
            
            while discovered_urls:
                discovered_url = discovered_urls.pop()
                url = discovered_url['url']
                
                scraping_result = self._scrape_page(url, analyzed_domain['delay'], discovered_url['depth'])
                if not scraping_result: continue  
                
                documents.append(scraping_result['document'])

                for discovered_url in scraping_result['discovered_urls']:
                    if any([is_url_blacklisted(discovered_url), 
                            urlsplit(discovered_url).netloc != analyzed_domain['target_domain']]): 
                        continue
                    discovered_urls.add({'url': discovered_url, 'depth': scraping_result['discovery_depth']})

                discovered_urls_dct[target_url].add(discovered_url)

            logger.info(f"Indexed {len(discovered_urls_dct[target_url])} new URLs for target URL '{target_url}'")
 
        write_urls_dictionary(discovered_urls_dct, 'discovered_urls')
        logger.info(f"Stored discovered URLs for target URL '{target_url}'")
        
        # Step 4: Clean documents, collect text and tags
        url_tags_dct       = load_urls_dictionary('url_tags')
        url_priorities_dct = load_urls_dictionary('url_priorities') 

        self._content_cleaner.perform_content_analysis(target_url)
        for document in documents:
            url = document.name
            self._content_cleaner.clean_furniture(document)
            self._content_cleaner.clean_repetitive_content(document)
            
            extracted_text = self._processor.convert_to_txt(document)
            url_filename = url_to_filename(url) 
            extracted_text_file_path = os.path.join(config.paths.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')
            with open(extracted_text_file_path, 'w') as f:
                f.write(extracted_text)
                logger.info(f"Saved extracted text for URL '{url}' under '{extracted_text_file_path}'")
            
            language = detect_language(extracted_text)
            topic, priority = detect_topic_and_priority(extracted_text, language)           
            url_tags_dct[url] = {
                'topic':    topic,
                'priority': priority,
                'language': language,
                'programs': self._processor.strategies_processor.apply_strategy(
                                strategy_name='programs', 
                                arguments={'document_content': extracted_text},
                            )
            }
            url_priorities_dct[priority].add(url)
            
        write_urls_dictionary(url_tags_dct, 'url_tags')
        write_urls_dictionary(url_priorities_dct, 'url_priorities')

        return results


    def _scrape_page(self, url: str, crawl_delay: float, discovery_depth: int = 0) -> dict:
        if not url: return None

        logger.info(f"Fetching URL '{url}'...")
        response = call_with_exponential_backoff(fetch_url, args=(url,), delay=crawl_delay)
        if response['status'] == 'FAIL':
            logger.warning("Failed to fetch URL '{url}': {response['last_error']}! Skipping...")
            return None
        if not response['result']:
            logger.warning("Cannot fetch '{url}'! Skipping...")
            return None
        
        raw_html = response['result']
        
        url_filename = url_to_filename(url) 
        raw_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
        with open(raw_html_file_path, 'w') as f:
            f.write(raw_html)
            logger.info(f"Saved fetched HTML under '{raw_html_file_path}'")

        logger.info(f"Processing URL '{url}'...")
        document = self._processor.process(url, raw_html)
        
        if not document:
            logger.warning(f"Failed to process URL '{url}'! Sipping...")
            return None
        
        discovered_urls = self._content_cleaner.extract_urls(document) if discovery_depth <= 3 else []
        self._content_cleaner.collect_repetitive_content(document)
        
        raw_text = self._processor.convert_to_txt(document)
        raw_text_file_path = os.path.join(config.paths.RAW_TEXT_OUTPUT, url_filename + '.txt')
        with open(raw_text_file_path, 'w') as f:
            f.write(raw_text)
            logger.info(f"Saved raw text for URL '{url}' under '{raw_text_file_path}'")

        return {
            'document': document,
            'discovered_urls': discovered_urls,
            'discovery_depth': discovery_depth + 1,
        }
   

    def _analyze_domain(self, target_url: str) -> dict:
        if not target_url:
            logger.warning('The target URL string is empty!')
            return None
       
        # Step 1: Test whether the target URL is even accessible before initializing the scraping procedure
        response = call_with_exponential_backoff(fetch_url, args=(target_url,))
        if response['status'] == 'FAIL':
            logger.error(f"Unaccessible target URL '{target_url}': {response['last_error']}")
            return None
        if not response['result']:
            logger.warning(f"Unnaccessible target URL '{target_url}': Recieved client/server error!")
            return None
        
        # Step 2: Fetch and parse robots
        logger.info(f"Fetching 'robots.txt' for the target URL '{target_url}'...")
        robots_parser: RobotFileParser = parse_robots(target_url)
        
        if not robots_parser:
            logger.warning(
                f"Could not fetch the 'robots.txt' file for the target URL '{target_url}'! " +
                 "(Are you sure the scraping begins from root?)"
            )
            return None
        
        logger.info(f"Parsed the 'robots.txt' file for target URL '{target_url}'")

        delay = robots_parser.crawl_delay('scraper')
        target_domain = urlsplit(target_url).netloc
        
        # Step 3: Fetch and parse sitemaps
        logger.info(f"Fetching sitemaps for target URL {target_url}...")
        sitemap_tree = sitemap_tree_for_homepage(target_url)
        if isinstance(sitemap_tree, InvalidSitemap):
            logger.error(f"Cannot fetch sitemap for target URL '{target_url}': Invalid sitemap structure!")
            return None
        urls = set([page.url for page in sitemap_tree.all_pages()])
        urls = [url for url in urls if robots_parser.can_fetch('scraper', url)]
        logger.info(f'Loaded sitemaps with {len(urls)} pages')

        return {
            'target_domain': target_domain,
            'sitemap_urls': urls,
            'delay': delay,
        }

