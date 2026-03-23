import os, datetime, shutil
from collections import Counter
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from usp.objects.sitemap import InvalidSitemap
from usp.tree import sitemap_tree_for_homepage

from .utils import *
from .html_processor  import HTMLProcessor
from .content_cleaner import ContentCleaner

from ..pipeline.utilclasses import ProcessingResult
from ..utils.lang import detect_language 
from ..utils.logging import get_logger
from ..config import config

logger = get_logger('scraper.core')

class Scraper:
    def __init__(self) -> None:
        self._processor:       HTMLProcessor  = HTMLProcessor()
        self._content_cleaner: ContentCleaner = ContentCleaner()
        
        os.makedirs(config.paths.URLS_OUTPUT,           exist_ok=True)
        os.makedirs(config.paths.CHUNKS_OUTPUT,         exist_ok=True)
        os.makedirs(config.paths.SCRAPING_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.RAW_HTML_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.RAW_TEXT_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.METADATA_OUTPUT,       exist_ok=True)
        os.makedirs(config.paths.EXTRACTED_TEXT_OUTPUT, exist_ok=True)

        logger.info(f'Successfully initialized the scraper')


    def scrape_target(self, target_url: str) -> list[ProcessingResult]:
        # Step 1: Analyze the target URL for fetching, robots and sitemap
        analyzed_domain = self._analyze_domain(target_url)
        if not analyzed_domain:
            logger.error(f"Failed to scrape target URL '{target_url}'")
            return []
        
        documents        = list()
        visited_urls     = set()
        discovered_urls  = set() 
        sitemap_urls_dct = load_set_dict(config.paths.URLS_OUTPUT, 'sitemap_urls', target_url)
        
        # Step 2: Validate and scrape URLs listed in the sitemap
        logger.info(f'Starting validation and scraping for sitemap URLs...')
        for url in analyzed_domain['sitemap_urls']:
            if is_url_blacklisted(url):
                logger.info(f"URL '{url}' is blacklisted by scraper, skipping...")
                continue
            if url in visited_urls:
                logger.info(f'URL {url} was already analyzed via redirect, skipping...')
                continue

            scraping_result = self._scrape_page(url, analyzed_domain['delay'])
            if not scraping_result: continue  
            
            documents.append(scraping_result['document'])
            sitemap_urls_dct[target_url].add(scraping_result['final_url'])
            visited_urls.add(scraping_result['final_url'])
            visited_urls.add(url)

            for discovered_url in scraping_result['discovered_urls']: 
                if any([is_url_blacklisted(discovered_url),
                        discovered_url in visited_urls,
                        urlsplit(discovered_url).netloc != analyzed_domain['target_domain']]): 
                    continue
                discovered_urls.add(discovered_url)

        logger.info(f"Indexed {len(sitemap_urls_dct[target_url])} " +
                    f"out of {len(analyzed_domain['sitemap_urls'])} " +
                    f"sitemap URLs for target URL '{target_url}'")
        
        write_set_dict(config.paths.URLS_OUTPUT, 'sitemap_urls', sitemap_urls_dct)
        logger.info(f"Stored sitemap URLs for target URL '{target_url}'")
        
        #Step 3: Analyze discovered URLs and search for the new ones
        discovered_urls = [{'url': url, 'depth': 0} for url in discovered_urls 
                           if url not in visited_urls]
        discovered_urls_dct = load_set_dict(config.paths.URLS_OUTPUT, 'discovered_urls', target_url)

        logger.info(f"Discovered {len(discovered_urls)} unique URLs while scraping the sitemap URLs")

        if discovered_urls:
            logger.info(f"Starting validation and scraping for discovered URLs...")
            
            while discovered_urls:
                discovered_url = discovered_urls.pop()
                url = discovered_url['url']

                scraping_result = self._scrape_page(url, analyzed_domain['delay'], discovered_url['depth'])
                if not scraping_result: continue  
                
                documents.append(scraping_result['document'])
                discovered_urls_dct[target_url].add(scraping_result['final_url'])
                visited_urls.add(scraping_result['final_url'])
                visited_urls.add(discovered_url['url'])

                for discovered_url in scraping_result['discovered_urls']:
                    if any([is_url_blacklisted(discovered_url),
                            discovered_url in visited_urls,
                            urlsplit(discovered_url).netloc != analyzed_domain['target_domain']]): 
                        continue
                    discovered_urls.append({'url': discovered_url, 'depth': scraping_result['discovery_depth']})


            logger.info(f"Indexed {len(discovered_urls_dct[target_url])} new URLs for target URL '{target_url}'")
 
        write_set_dict(config.paths.URLS_OUTPUT, 'discovered_urls', discovered_urls_dct)
        logger.info(f"Stored discovered URLs for target URL '{target_url}'")
        
        # Step 4: Clean documents, collect text and tags
        url_tags_dct       = load_set_dict(config.paths.URLS_OUTPUT, 'url_tags')
        url_priorities_dct = load_set_dict(config.paths.URLS_OUTPUT, 'url_priorities')
        chunk_metadata_dct = load_set_dict(config.paths.METADATA_OUTPUT, 'chunk_metadata_dct')
        chunk_metadata_dct[target_url] = []
        program_counter = Counter()

        self._content_cleaner.perform_content_analysis(target_url)
        for document in documents:
            url = document.name
            chunk_metadata_dct[url] = []
            self._content_cleaner.clean_document(document)
            
            extracted_text = self._processor.convert_to_txt(document)
            url_filename = url_to_filename(url) 
            extracted_text_file_path = os.path.join(config.paths.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')
            with open(extracted_text_file_path, 'w') as f:
                f.write(extracted_text)
                logger.info(f"Saved extracted text for URL '{url}' under '{extracted_text_file_path}'")
            
            language = detect_language(extracted_text)
            topic, priority = detect_topic_and_priority(extracted_text, language)
            programs = self._processor.strategies_processor.apply_strategy(
                strategy_name='programs', 
                arguments={'document_content': extracted_text},
            )
            program = programs[0] if programs else 'None'
            program_counter[program] += 1
 
            url_tags = {
                'topic':    topic,
                'priority': priority,
                'language': language,
                'program':  programs,
            }
            url_tags_dct[url] = url_tags
            url_priorities_dct[priority].add(url)

            # Step 5: Collect and save chunks
            doc_chunks_dir_path = os.path.join(config.paths.CHUNKS_OUTPUT, url_filename)
            if os.path.exists(doc_chunks_dir_path):
                shutil.rmtree(doc_chunks_dir_path)
            os.makedirs(doc_chunks_dir_path)
            
            url_chunk_metadata_list = []
            for i, chunk in enumerate(self._processor.chunk(document), start=1):
                chunk_file_path = os.path.join(doc_chunks_dir_path, f"chunk_{i}.txt")
                with open(chunk_file_path, 'w') as f:
                    f.write(chunk['text'])

                url_chunk_metadata_list.append({
                    'chunk_id': f"{program.lower()}_{program_counter[program]:3d}_{i:2d}",
                    'text': chunk['text'],
                    'source_url': url,
                    'program':  program,
                    'language': url_tags['language'],
                    'topic': url_tags['topic'],             #TODO: Topic classification pro chunk
                    'last_scraped': datetime.datetime.now(),
                    'page_title': self._processor.extract_title(document),
                    'section_heading': chunk['title'],
                    'token_size': chunk['size'],
                })
            
            chunk_metadata_dct[target_url].extend(url_chunk_metadata_list)     
            logger.info(f"Collected {i} chunks and saved under '{doc_chunks_dir_path}'")
            
        write_set_dict(config.paths.URLS_OUTPUT, 'url_tags', url_tags_dct)
        write_set_dict(config.paths.URLS_OUTPUT, 'url_priorities', url_priorities_dct)
        write_set_dict(config.paths.METADATA_OUTPUT, 'chunk_metadata', chunk_metadata_dct)

        return 


    def _scrape_page(self, url: str, crawl_delay: float, discovery_depth: int = 0) -> dict:
        if not url: return {}

        logger.info(f"Fetching URL '{url}'...")
        response = call_with_exponential_backoff(fetch_url, args=(url,), delay=crawl_delay)
        if response['status'] == 'FAIL':
            logger.warning("Failed to fetch URL '{url}': {response['last_error']}! Skipping...")
            return {}
        fetch_result = response['result']
        if not fetch_result:
            logger.warning("Cannot fetch '{url}'! Skipping...")
            return {}
        
        raw_html  = fetch_result['text']
        final_url = fetch_result['final_url']
        
        if final_url != url:
            logger.info(f"Redirect detected: '{url}' --> '{final_url}'")
            logger.info(f"Continuing with URL '{final_url}'...")

        url_filename = url_to_filename(final_url) 
        raw_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
        with open(raw_html_file_path, 'w') as f:
            f.write(raw_html)
            logger.info(f"Saved fetched HTML under '{raw_html_file_path}'")

        logger.info(f"Processing URL '{final_url}'...")
        document = self._processor.process(final_url, raw_html)
        
        if not document:
            logger.warning(f"Failed to process URL '{final_url}'! Sipping...")
            return {}
        
        discovered_urls = self._content_cleaner.extract_urls(document) if discovery_depth <= 3 else []
        self._content_cleaner.collect_repetitive_content(document)
        
        raw_text = self._processor.convert_to_txt(document)
        raw_text_file_path = os.path.join(config.paths.RAW_TEXT_OUTPUT, url_filename + '.txt')
        with open(raw_text_file_path, 'w') as f:
            f.write(raw_text)
            logger.info(f"Saved raw text for URL '{final_url}' under '{raw_text_file_path}'")

        return {
            'document': document,
            'final_url': final_url,
            'discovered_urls': discovered_urls,
            'discovery_depth': discovery_depth + 1,
        }
   

    def _analyze_domain(self, target_url: str) -> dict:
        if not target_url:
            logger.warning('The target URL string is empty!')
            return {}
       
        # Step 1: Test whether the target URL is even accessible before initializing the scraping procedure
        response = call_with_exponential_backoff(fetch_url, args=(target_url,))
        if response['status'] == 'FAIL':
            logger.error(f"Unaccessible target URL '{target_url}': {response['last_error']}")
            return {}
        if not response['result']:
            logger.warning(f"Unnaccessible target URL '{target_url}': Recieved client/server error!")
            return {}
        
        # Step 2: Fetch and parse robots
        logger.info(f"Fetching 'robots.txt' for the target URL '{target_url}'...")
        robots_parser: RobotFileParser = parse_robots(target_url)
        
        if not robots_parser:
            logger.warning(
                f"Could not fetch the 'robots.txt' file for the target URL '{target_url}'! " +
                 "(Are you sure the scraping begins from root?)"
            )
            return {}
        
        logger.info(f"Parsed the 'robots.txt' file for target URL '{target_url}'")

        delay = robots_parser.crawl_delay('scraper')
        target_domain = urlsplit(target_url).netloc
        
        # Step 3: Fetch and parse sitemaps
        logger.info(f"Fetching sitemaps for target URL {target_url}...")
        sitemap_tree = sitemap_tree_for_homepage(target_url)
        if isinstance(sitemap_tree, InvalidSitemap):
            logger.error(f"Cannot fetch sitemap for target URL '{target_url}': Invalid sitemap structure!")
            return {}
        urls = set([page.url for page in sitemap_tree.all_pages()])
        urls = [url for url in urls if robots_parser.can_fetch('scraper', url)]
        logger.info(f'Loaded sitemaps with {len(urls)} pages')

        return {
            'target_domain': target_domain,
            'sitemap_urls': urls,
            'delay': delay,
        }

