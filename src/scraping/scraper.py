import os, shutil, json
from datetime import datetime
from collections import Counter
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from usp.objects.sitemap import InvalidSitemap
from usp.tree import sitemap_tree_for_homepage

from .utils import *
from .types import *
from .html_processor  import HTMLProcessor
from .content_cleaner import ContentCleaner
from .url_normalizer import UrlNormalizer

from ..utils.lang import detect_language 
from ..utils.logging import get_logger
from ..config import config

logger = get_logger('scraper.core')
incupd_logger = get_logger('scraper.incremental_updates')

class Scraper:
    def __init__(self, scrape_all: bool =True) -> None:
        self._scrape_all = scrape_all
        self._path       = config.paths
        self._processor:       HTMLProcessor  = HTMLProcessor()
        self._normalizer:      UrlNormalizer  = UrlNormalizer()
        self._content_cleaner: ContentCleaner = ContentCleaner()

        self._make_directories()
        
        self._url_timestamps: dict[str, UrlTimestamps] = self._load_data(self._path.SCRAPING_OUTPUT, 'url_timestamps')
        self._url_priorities: dict[str, list[str]] = self._load_data(self._path.URLS_OUTPUT, 'url_priorities')

        logger.info(f'Successfully initialized the scraper')
   

    def _make_directories(self) -> None:
        os.makedirs(self._path.URLS_OUTPUT,           exist_ok=True)
        os.makedirs(self._path.CHUNKS_OUTPUT,         exist_ok=True)
        os.makedirs(self._path.SCRAPING_OUTPUT,       exist_ok=True)
        os.makedirs(self._path.RAW_HTML_OUTPUT,       exist_ok=True)
        os.makedirs(self._path.RAW_TEXT_OUTPUT,       exist_ok=True)
        os.makedirs(self._path.METADATA_OUTPUT,       exist_ok=True)
        os.makedirs(self._path.EXTRACTED_TEXT_OUTPUT, exist_ok=True)


    def scrape_target(self, target_url: str) -> list[ChunkMetadata]:
        # Step 1: Analyze the target URL for availability, robots and sitemap
        analyzed_domain = self._analyze_domain(target_url)
        if not analyzed_domain:
            logger.error(f"Failed to scrape target URL {target_url}")
            return []

        sitemap_urls = analyzed_domain.urls 
        self._save_results(self._path.URLS_OUTPUT, 'sitemap_urls', sitemap_urls, target_url)

        # Step 2: Validate and scrape URLs listed in the sitemap
        analyzed_sitemap = self._analyze_sitemap(analyzed_domain) 

        documents = analyzed_sitemap.documents

        logger.info(f"Indexed {len(sitemap_urls)} sitemap URLs for target URL {target_url}")
        logger.info(f"Scraped {len(documents)} unique URLs (others were either redirects or blacklisted)")

        #Step 3: Analyze discovered URLs and search for the new ones
        discovered_urls = analyzed_sitemap.discovered_urls
        logger.info(f"Discovered {len(discovered_urls)} new URLs during sitemap analysis")
        
        analyzed_discoveries = self._analyze_discoveries(discovered_urls, sitemap_urls, analyzed_domain)

        discovered_urls = analyzed_discoveries.discovered_urls
        self._save_results(self._path.URLS_OUTPUT, 'discovered_urls', discovered_urls, target_url) 

        documents.extend(analyzed_discoveries.documents)

        logger.info(f"Indexed {len(discovered_urls)} new URLs for target URL {target_url}")
       
        if not documents:
            logger.info(f"No new content was scraped from the target URL {target_url}")
            return []

        self._save_results(self._path.SCRAPING_OUTPUT, 'url_timestamps', self._url_timestamps)

        # Step 4: Clean documents, collect text and tags
        self._content_cleaner.perform_content_analysis(target_url, self._normalizer.url_to_filename(target_url))
        analyzied_documents = self._analyze_url_documents(documents)
        
        self._save_results(self._path.URLS_OUTPUT, 'url_tags',       analyzied_documents.url_tags)
        self._save_results(self._path.URLS_OUTPUT, 'url_priorities', analyzied_documents.url_priorities)

        # Step 5: Collect and save chunks
        chunk_metadatas = self._collect_chunks(analyzied_documents.tagged_documents)
        
        self._save_results(self._path.METADATA_OUTPUT, 'raw_chunk_metadata',     chunk_metadatas['raw'],     target_url)
        self._save_results(self._path.METADATA_OUTPUT, 'merged_chunk_metadata',  chunk_metadatas['merged'],  target_url)
        self._save_results(self._path.METADATA_OUTPUT, 'deleted_chunk_metadata', chunk_metadatas['deleted'], target_url)
        
        logger.info(f"Collected {len(chunk_metadatas['merged'])} chunks from target URL {target_url}")

        logger.info(f"Scraping finished for target URL '{target_url}'")
        return chunk_metadatas['merged'] 


    def _analyze_domain(self, target_url: str) -> DomainAnalysisReport | None:
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
        
        page_data = []
        page_urls = set()
        for page in sitemap_tree.all_pages():
            page_url = page.url 
            if not robots_parser.can_fetch('scraper', page_url) or page_url in page_urls:
                continue

            page_urls.add(page_url)
            page_data.append(PageData(page_url, page.last_modified))

        logger.info(f'Loaded sitemaps with {len(page_data)} pages')

        return DomainAnalysisReport(
            target = target_domain,
            urls   = list(page_urls),
            pages  = page_data,
            delay  = delay,
        )
    

    def _analyze_sitemap(self, domain: DomainAnalysisReport) -> UrlAnalysisReport:
        documents = []
        visited_urls    = set()
        discovered_urls = set()

        sitemap_pages = domain.pages
        logger.info(f'Starting validation and scraping for sitemap URLs...')
        for page in sitemap_pages:
            result = self._scrape_page(page.url, domain.delay, visited_urls, last_modified=page.last_modified)
            visited_urls.add(page.url)

            if not result: continue  
            
            final_url = result.final_url
            documents.append(result.document)
            visited_urls.add(final_url)

            self._store_timestamps(final_url, result.timestamps)
            
            new_urls = self._normalizer.filter_discovered_urls(result.discovered_urls, visited_urls, domain.target)
            discovered_urls |= new_urls
        
        discovered_urls = [url for url in discovered_urls if url not in visited_urls]
        return UrlAnalysisReport(
            documents       = documents,
            discovered_urls = discovered_urls,
        )


    def _analyze_discoveries(self, discovered_urls: list, sitemap_urls: list, domain: DomainAnalysisReport) -> UrlAnalysisReport:
        if len(discovered_urls) == 0:
            return UrlAnalysisReport([], [])

        documents = []
        discoveries  = discovered_urls.copy()
        visited_urls = set(sitemap_urls.copy())
        
        discovered_urls = [{'url': url, 'depth': 0} for url in discovered_urls]
        logger.info(f"Starting validation and scraping for discovered URLs...")
        while discovered_urls:
            discovered_url = discovered_urls.pop()
            url = discovered_url['url']

            result = self._scrape_page(url, domain.delay, visited_urls, discovery_depth=discovered_url['depth'])
            visited_urls.add(url)
            
            if not result: continue  
            
            final_url = result.final_url
            documents.append(result.document)
            visited_urls.add(final_url)
            discoveries.append(final_url)
            
            self._store_timestamps(final_url, result.timestamps)

            for new_url in self._normalizer.filter_discovered_urls(result.discovered_urls, visited_urls, domain.target):
                discovered_urls.append({'url': new_url, 'depth': result.discovery_depth})

        return UrlAnalysisReport(
            documents       = documents,
            discovered_urls = discoveries,
        )


    def _analyze_url_documents(self, documents: list) -> DocumentAnalysisReport:
        url_tags = {}
        url_priorities = defaultdict(list)
        tagged_documents = []

        logger.info(f"Analyzing scraped contents of {len(documents)} pages...")
        for document in documents:
            url = document.name
            self._content_cleaner.clean_document(document)
            
            extracted_text = self._processor.convert_to_txt(document)
            url_filename = self._normalizer.url_to_filename(url) 
            extracted_text_file_path = os.path.join(self._path.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')
            
            with open(extracted_text_file_path, 'w') as f:
                f.write(extracted_text)
                logger.info(f"Saved extracted text for URL '{url}' under '{extracted_text_file_path}'")
            
            language  = detect_language(extracted_text)
            tp_result = detect_page_topic_and_priority(extracted_text)
            programs  = self._processor.strategies_processor.apply_strategy(
                strategy_name='programs', 
                arguments={'document_content': extracted_text},
            )
            program = programs[0] if programs else 'no program'

            tags = UrlTags(
                topic    = tp_result['topic'],
                priority = tp_result['priority'],
                language = language,
                program  = program,
            )

            url_tags[url] = tags
            url_priorities[tp_result['priority']].append(url)
            
            tagged_documents.append(TaggedDocument(document, DocumentTags(program, language)))

        return DocumentAnalysisReport(
            url_tags         = url_tags,
            url_priorities   = url_priorities,
            tagged_documents = tagged_documents,
        )


    def _collect_chunks(self, tagged_documents: list[dict]) -> dict[str, list[ChunkMetadata]]:
        program_counter = Counter()
        raw_chunks      = []
        deleted_chunks  = []
        merged_chunks   = []

        for entry in tagged_documents:
            document = entry.document
            program  = entry.tags.program 
            language = entry.tags.language
            url = document.name
            url_filename = self._normalizer.url_to_filename(url)
            
            program_counter[program] += 1
 
            doc_chunks_dir_path = os.path.join(config.paths.CHUNKS_OUTPUT, url_filename) 
            if os.path.exists(doc_chunks_dir_path): shutil.rmtree(doc_chunks_dir_path)
            os.makedirs(doc_chunks_dir_path)
            
            mergible_chunks_metadatas = []
            for i, chunk in enumerate(self._processor.chunk(document), start=1):
                chunk_file_path = os.path.join(doc_chunks_dir_path, f"chunk_{i}.txt")
                with open(chunk_file_path, 'w') as f:
                    f.write(chunk['text'])
                
                chunk_topic = detect_chunk_topic(chunk['text'])
                chunk_metadata = ChunkMetadata(
                    chunk_id        = f"{program.lower()}_{program_counter[program]:3d}_{i:2d}",
                    text            = chunk['text'],
                    source_url      = url,
                    program         =  program,
                    language        = language,
                    topic           = chunk_topic,             
                    last_scraped    = datetime.now(),
                    page_title      = self._processor.extract_title(document),
                    section_heading = chunk['title'],
                    token_size      = chunk['size'],
                )
                raw_chunks.append(chunk_metadata)
                if chunk_topic == 'none':
                    deleted_chunks.append(chunk_metadata)
                else:
                    mergible_chunks_metadatas.append(chunk_metadata)

            logger.info(f"Collected {i} raw chunks and saved under '{doc_chunks_dir_path}'")
            
            merged_chunk_metadatas = self._processor.merge_chunks_by_topic(mergible_chunks_metadatas) 
            merged_chunks.extend(merged_chunk_metadatas) 
            logger.info(f"Merged raw chunks into {len(merged_chunk_metadatas)} chunks by topic")

        return {
            'raw':     raw_chunks,
            'merged':  merged_chunks,
            'deleted': deleted_chunks,
        }


    def _is_url_modified(
        self, 
        url: str, 
        new_last_modified: datetime | None = None,
        new_page_hash: str | None = None
    ) -> bool:
        if url not in self._url_timestamps.keys():
            return True

        stored = self._url_timestamps[url]

        if stored.last_modified and new_last_modified:
            return stored.last_modified < new_last_modified

        if new_page_hash and stored.page_hash:
            return new_page_hash != stored.page_hash

        return True
    

    def _store_timestamps(self, url: str, timestamps: UrlTimestamps) -> None:
        self._url_timestamps[url] = timestamps


    def _get_etag(self, url: str) -> str | None:
        if url not in self._url_timestamps.keys():
            return None 

        return self._url_timestamps[url].etag
    

    def _is_fetch_valid(self, url: str, visited_urls: list[str], fetch_result: FetchResult) -> bool:
        if not fetch_result:
            logger.warning(f"Cannot fetch {url}! Skipping...")
            return False

        if fetch_result.not_modified:
            logger.info("No updates on the page, skipping...")
            return False
    
        final_url = fetch_result.final_url
        if final_url != url:
            logger.info(f"Redirect detected: '{url}' --> '{final_url}'")
            if final_url in visited_urls:
                logger.info(f"'{final_url}' was already visited, skipping...")
                return False
            logger.info(f"Continuing with URL '{final_url}'...")
        
        last_modified = fetch_result.last_modified
        page_hash = fetch_result.page_hash
        if not self._is_url_modified(final_url, new_last_modified=last_modified, new_page_hash=page_hash):
            logger.info(f"URL {final_url} was not modified since last scraping session, skipping...")
            return False 
        
        return True


    def _scrape_page(
        self, url: str, 
        crawl_delay: float, 
        visited_urls: list[str], 
        discovery_depth: int = 0,
        last_modified: datetime | None = None
    ) -> ScrapingResult | None:
        if not url: 
            return None
        
        if self._normalizer.is_url_blacklisted(url):
            logger.info(f"URL {url} is blacklisted by scraper, skipping...")
            return None

        if url in visited_urls:
            logger.info(f'URL {url} was already analyzed via redirect, skipping...')
            return None
        

        if not self._scrape_all and last_modified and not self._is_url_modified(url, new_last_modified=last_modified):
            logger.info(f"URL '{url}' was not modified since last scraping session, skipping...")
            self._url_timestamps[url].last_modified = last_modified
            return None 

        logger.info(f"Fetching head for URL '{url}'...")
        
        etag = self._get_etag(url)
        response = call_with_exponential_backoff(fetch_head, args=(url, etag), delay=crawl_delay) 
        if response['status'] == 'FAIL':
            logger.warning(f"Failed to fetch head for URL {url}: {response['last_error']}! Skipping...")
            return None 
        
        fetch_result = response['result']
        if not self._is_fetch_valid(url, visited_urls, fetch_result):
            return None

        response = call_with_exponential_backoff(fetch_url, args=(url, etag), delay=crawl_delay)
        if response['status'] == 'FAIL':
            logger.warning(f"Failed to fetch URL {url}: {response['last_error']}! Skipping...")
            return None 

        fetch_result = response['result']
        if not self._is_fetch_valid(url, visited_urls, fetch_result):
            return None
        
        if not fetch_result.last_modified:
            logger.warning("No information about URL last modification date exists!")

        timestamps = UrlTimestamps(
            last_modified = fetch_result.last_modified,
            last_scraped  = datetime.now(),
            etag          = fetch_result.etag,
            page_hash     = fetch_result.page_hash,
        )
 
        raw_html  = fetch_result.text
        final_url = fetch_result.final_url
        
        url_filename = self._normalizer.url_to_filename(final_url) 
        raw_html_file_path = os.path.join(config.paths.RAW_HTML_OUTPUT, url_filename + '.html')
        with open(raw_html_file_path, 'w') as f:
            f.write(raw_html)
            logger.info(f"Saved fetched HTML under '{raw_html_file_path}'")
        
        logger.info(f"Cleaning URL {final_url} from mobile data...")
        cleaned_html = self._content_cleaner.clean_mobile_content(raw_html)

        logger.info(f"Processing URL {final_url}...")
        document = self._processor.process(final_url, cleaned_html)
        
        if not document:

            logger.warning(f"Failed to process URL '{final_url}'! Skipping...")
            return None
        
        discovered_urls = self._content_cleaner.extract_urls(document) if discovery_depth <= 3 else []
        self._content_cleaner.collect_repetitive_content(document)
        
        raw_text = self._processor.convert_to_txt(document)
        raw_text_file_path = os.path.join(config.paths.RAW_TEXT_OUTPUT, url_filename + '.txt')
        with open(raw_text_file_path, 'w') as f:
            f.write(raw_text)
            logger.info(f"Saved raw text for URL '{final_url}' under '{raw_text_file_path}'")

        return ScrapingResult(
            document        = document,
            discovered_urls = discovered_urls,
            final_url       = final_url,
            timestamps      = timestamps,
            discovery_depth = discovery_depth+1,
        )


    def _save_results(self, path: str, filename: str, results, target_url: str | None = None) -> None:
        results_path = os.path.join(path, filename + '.json')
        
        results_dict = {}
        if os.path.exists(results_path):
            try:
                with open(results_path, 'r', encoding='utf-8') as f:
                    results_dict = json.load(f)
            except Exception:
                logger.warning(f"Failed to load existing {results_path}, will overwrite")
        
        if filename == 'url_tags':
            results_dict |= results

        elif filename == 'url_timestamps':
            for url, ts in results.items():
                results_dict[url] = dataclass_to_dict(ts)
        
        elif filename == 'url_priorities':
            for prio, urls in results.items():
                prev = set(results_dict.get(prio, []))
                results_dict[prio] = list(prev.union(urls))
        
        else:

            results = [dataclass_to_dict(r) for r in results]
            if target_url: 
                results_dict[target_url] = results
            else:
                results_dict = results
        
        try: 
            with open(results_path, 'w', encoding='utf-8') as f:
                json.dump(results_dict, f, indent=4, 
                    default=lambda o: o.isoformat() if isinstance(o, datetime) else None)
        except Exception as e:
            logger.error(f"Failed to store results '{filename}'")
            raise e
    
        logger.info(f"Stored results in file {results_path}")


    def _load_data(self, path: str, filename: str) -> dict:
        datapath = os.path.join(path, filename + '.json')
        
        if not os.path.exists(datapath):
            logger.warning(f"Failed to load/locate file {datapath}; new data will be recorded")
            return defaultdict(dict)
        
        try:
            with open(datapath, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            if filename == 'url_timestamps':
                for url, ts_dict in loaded_data.items():
                    loaded_data[url] = dict_to_url_timestamps(ts_dict) 
                incupd_logger.info(f"Loaded {len(loaded_data)} URL timestamps")
            else:
                incupd_logger.info(f"Loaded data '{filename}'")
            
            return loaded_data
            
        except Exception as e:
            incupd_logger.error(f"Failed trying to load data '{filename}': {e}")
            incupd_logger.info("New data will be recorded")
            return defaultdict(dict)


