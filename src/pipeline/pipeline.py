from .utils import *
from .processors import *
from ..scraping.scraper import Scraper
from ..scraping.types import ScrapeManifest

from ..database.weavservice import SourceReconciliationSummary, WeaviateService
from ..utils.logging import get_logger
from ..utils.tools import call_with_exponential_backoff
from ..config import config

pipelogger = get_logger("pipeline_module")
implogger  = get_logger("import_pipeline")


class ImportPipeline:
    """
    Import website and local documents with source-level safe replacement.
    """

    def __init__(
        self, 
        logging_callback = None,
        deduplication_callback = None,
    ) -> None:
        """
        Initialize processors and optional UI callbacks.

        Args:
            logging_callback (callable, optional): A callback function for logging progress.
                Defaults to a placeholder if not provided.
            deduplication_callback (callable, optional): For existing local sources,
                returns True to replace the source or False to append without cleanup.
        """
        self._logging_callback = logging_callback or logging_callback_placeholder
        self._deduplication_callback = deduplication_callback
        self._docprocessor = DocumentProcessor()
        self._service      = WeaviateService()
        
        implogger.info('Import pipeline initialization finished!')
    

    def import_from_scraper(
        self,
        manifest: ScrapeManifest,
    ) -> list[SourceReconciliationSummary]:
        rows_by_source = {
            source: {
                lang: []
                for lang in config.get('AVAILABLE_LANGUAGES')
            }
            for source in manifest.processed_sources
        }
        for lang, chunks in manifest.chunks_by_language.items():
            for chunk in chunks:
                source = chunk.get('source', '')
                if source in rows_by_source:
                    rows_by_source[source].setdefault(lang, []).append(chunk)

        return [
            self._service.reconcile_source(source, rows_by_source[source])
            for source in manifest.processed_sources
        ]


    def scrape_website(self, target_urls: list[str] | None = None, scrape_all: bool = False) -> None:
        target_urls = [url for url in (target_urls or config.scraping.TARGET_URLS or []) if url]
        if not target_urls:
            implogger.warning("No target URLs configured for scraping.")
            return

        def scrape() -> None:
            try:
                scraper = Scraper(scrape_all=scrape_all)
                for target_url in target_urls:
                    self._logging_callback(f"Scraping target {target_url}...", 0)
                    manifest = scraper.scrape_target(target_url)
                    if not manifest:
                        self._logging_callback(f"No importable chunks scraped from {target_url}.", 100)
                        continue

                    self._logging_callback(f"Importing scraped chunks from {target_url}...", 90)
                    self.import_from_scraper(manifest)
                    scraper.commit_scrape(manifest)
                    self._logging_callback(f"Finished scraping import for {target_url}.", 100)
            except Exception as e:
                implogger.error(f"Scraping task was interrupted: {e}")
                raise e

        result = call_with_exponential_backoff(scrape)
        if result["status"] != "OK":
            raise result["last_error"]


    def import_many_documents(self, sources: list[str]) -> None:
        self.import_all(paths=sources)


    def _import_urls_via_scraper(self, urls: list[str], scrape_all: bool = True) -> None:
        urls = [url for url in (urls or []) if url]
        if not urls:
            return

        scraper = Scraper(scrape_all=scrape_all)
        for url in urls:
            self._logging_callback(f"Scraping URL {url}...", 0)
            manifest = scraper.scrape_target(url)
            if not manifest:
                self._logging_callback(f"Failed to scrape URL {url}!", 100, failed=True)
                continue

            self._logging_callback(f"Importing scraped chunks from {url}...", 90)
            self.import_from_scraper(manifest)
            scraper.commit_scrape(manifest)
            self._logging_callback(f"Stored scraped chunks for {url}.", 100)
                 
        
    def import_all(
            self, 
            paths: list[str] = None,
            urls:  list[str] = None,
            reset_collections: bool = False,
        ) -> None:
        """
        Import documents from local paths and/or URLs into the database.

        Processes the provided paths and URLs using the appropriate processors,
        combines chunks by language, optionally resets database collections,
        and performs batch imports.

        Args:
            paths (list[str], optional): List of local file paths to process. Defaults to None.
            urls (list[str], optional): List of website URLs to process. Defaults to None.
            reset_collections (bool, optional): If True, reset the database collections before importing.
                Defaults to False.
        """
        results = self._process_documents(paths, fail_fast=reset_collections)

        if reset_collections:
            chunks_by_language = {
                lang: []
                for lang in config.get('AVAILABLE_LANGUAGES')
            }
            for result in results:
                chunks_by_language[result.lang].extend(result.chunks)

            prepared_by_language = {
                lang: self._service.prepare_batch_import(chunks, lang)
                for lang, chunks in chunks_by_language.items()
            }
            self._logging_callback(
                'Resetting database collections (destructive operation)...',
                60,
            )
            self._service._reset_collections()
            for lang, prepared in prepared_by_language.items():
                self._service._write_prepared_rows(prepared, lang)
        else:
            for result in results:
                self._import_document_result(result)

        self._import_urls_via_scraper(urls, scrape_all=True)

        self._logging_callback(
            f'Successfully imported {sum(len(result.chunks) for result in results)} document chunks!',
            100
        )


    def _process_documents(
        self,
        sources: list[str] | None,
        fail_fast: bool = False,
    ) -> list[ProcessingResult]:
        results = []
        for source in [s for s in (sources or []) if s]:
            self._logging_callback(f'Starting pipeline for {source}...', 0)
            result = self._docprocessor.process(source)

            if not result.chunks:
                implogger.error(f"Failed to process {source}!")
                self._logging_callback(f"Failed to process {source}!", 100, result, failed=True)
                if fail_fast:
                    raise RuntimeError(
                        f"Aborting destructive collection reset because '{source}' "
                        "did not produce importable chunks"
                    )
                continue

            results.append(result)
            self._logging_callback(f'Prepared chunks for {source}.', 70, result)

        if sources and not results:
            self._logging_callback('No new data could be extracted from these sources!', 100)
            implogger.warning("Provided files did not contain importable information.")

        return results


    def _import_document_result(
        self,
        result: ProcessingResult,
    ) -> None:
        existing_count = self._service.source_object_count(result.source)
        should_replace = True
        if existing_count and self._deduplication_callback:
            should_replace = self._deduplication_callback(result.source, existing_count)

        if existing_count and should_replace:
            rows_by_language = {
                lang: []
                for lang in config.get('AVAILABLE_LANGUAGES')
            }
            rows_by_language[result.lang] = result.chunks
            self._service.reconcile_source(result.source, rows_by_language)
            return

        self._service.batch_import(result.chunks, result.lang)
