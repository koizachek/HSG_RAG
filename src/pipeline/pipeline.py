from src.pipeline.utilclasses import (
        _deduplication_callback_placeholder,
        _logging_callback_placeholder,
        ProcessingResult,
)
from src.pipeline.processors import *
from src.database.weavservice  import WeaviateService

from src.utils.logging import get_logger

from config import AVAILABLE_LANGUAGES

pipelogger = get_logger("pipeline_module")
implogger  = get_logger("import_pipeline")


class ImportPipeline:
    """
    Main pipeline class responsible for importing website and local documents
    into the database with deduplication and language-based organization.
    """

    def __init__(
        self, 
        logging_callback = None,
        deduplication_callback = None,
        reset_collections_on_import = False,
    ) -> None:
        """Initialize the import pipeline with processors and hashtable data."""
        self._reset_collections_on_import = reset_collections_on_import
        self._logging_callback = logging_callback or _logging_callback_placeholder
        self._deduplication_callback = deduplication_callback or _deduplication_callback_placeholder
        self._webprocessor = WebsiteProcessor(logging_callback)
        self._processor    = DocumentProcessor(logging_callback)
        self._wvtserv      = WeaviateService()
        self._ids          = self._wvtserv._collect_chunk_ids()
        
        implogger.info('Import pipeline initialization finished!')
        

    def _pipeline(self, sources: list, processor: ProcessorBase) -> dict:
        unique_chunks = {lang: [] for lang in AVAILABLE_LANGUAGES}
        
        for source in sources:
            self._logging_callback(f'Starting pipeline for {source}...', 0)
            result = processor.process(source)

            if not result:
                implogger.error(f"Failed to process document {source}!")
                continue
            
            chunks = result.chunks
            if not self._reset_collections_on_import:
                chunks = self._deduplicate(result)

            self._logging_callback(f'Storing chunks for {source}...', 100, result)

            if chunks:
                unique_chunks[result.lang].extend(chunks)

        if all([len(chunks) == 0 for chunks in unique_chunks.values()]):
            self._logging_callback('No new data could be extracted from these sources!', 100)
            implogger.warning(f"File(s) provided for the insertion do not contain any unique information. Terminating the pipeline without importing")
            return 
        
        self._logging_callback('Importing chunks to database...', 90)
        self._import_to_database(unique_chunks)
        self._logging_callback('Successfully processed all sources!', 100)


    def scrape(self, urls: list[str]):
        """
        Scrapes provided websites, process and deduplicate them,
        and import unique chunks into the database.

        Args:
            urls (list[str]): List of URLS to process.
        """
        self._pipeline(urls, self._webprocessor) 


    def import_documents(self, sources: list[str]):
        """
        Imports multiple sources (PDF, TXT, JSON, MD) by processing, deduplicating, and inserting
        unique chunks into the database.

        Args:
            sources (list[str]): List of file paths to process.
        """
        self._pipeline(sources, self._processor)
     
 
    def _deduplicate(self, result: ProcessingResult) -> list:
        """
        Remove duplicate chunks based on chunks that are already stored in the database.

        Args:
            source_name (str): Document name for deduplication callback.
            result (ProcessingResult): The processing result containing document chunks.

        Returns:
            list[dict]: List of unique chunk dictionaries.
        """
        if self._reset_collections_on_import:
            return result.chunks

        self._logging_callback('Performing deduplication...', 80)
        collected_chunks = result.chunks
        unique_chunks = []
        duplicate_ids = []
        for chunk in collected_chunks:
            chunk_id = chunk['chunk_id']
            if chunk_id in self._ids:
                duplicate_ids.append(chunk_id)
            else: 
                unique_chunks.append(chunk)
        
        implogger.info(f"Found {len(duplicate_ids)} already existing IDs in {len(collected_chunks)} collected chunks")
        if not unique_chunks:
            implogger.info(f"Calling deduplication callback...")
            if self._deduplication_callback(result.source, len(collected_chunks)):
                implogger.info('Duplicated chunks will be reimported as new...')
                self._wvtserv._delete_by_id(duplicate_ids)
                return collected_chunks

        return unique_chunks


    def _import_to_database(self, unique_chunks):
        """
        Import the processed unique chunks into the Weaviate database.

        Args:
            unique_chunks (dict): Dictionary mapping languages to lists of chunks.
        """
        if self._reset_collections_on_import:
            self._wvtserv._reset_collections()

        for lang, chunks in unique_chunks.items():
            if chunks:
                self._wvtserv.batch_import(data_rows=chunks, lang=lang)
