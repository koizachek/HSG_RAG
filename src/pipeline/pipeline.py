import os

from pathlib import Path
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

    def scrape_website(self):
        """
        Scrape program pages from the website, process and deduplicate them,
        and import unique chunks into the database.
        """
        unique_chunks = {lang: [] for lang in AVAILABLE_LANGUAGES}
        for result in self._webprocessor.process():
            chunks = self._deduplicate(result)
            unique_chunks[result.language].extend(chunks)

        if not unique_chunks:
            implogger.warning("Information provided by the HSG website does not contain any unique information. Terminating the pipeline without importing")
            return 
        
        self._import_to_database(unique_chunks)


    def import_many_documents(self, sources: list[Path | str]):
        """
        Import multiple documents by processing, deduplicating, and inserting
        unique chunks into the database.

        Args:
            sources (list[Path | str]): List of file paths or URLs to process.
        """
        if self._reset_collections_on_import:
            implogger.warning('Reset collection flag is set to True!')
            implogger.warning('All existing embeddings will be removed from database before imprting!')

        if 'all' in sources:
            implogger.info("Import list contains the 'all', all sources will be imported...")
            sources = _get_all_sources(sources)
        
        if not sources:
            implogger.warning("Import list does not contain any sources, aborting the import pipeline!")
            return

        if len(sources) > 1:
            implogger.info(f"Initiating the import pipeline for multiple sources: {', '.join(sources)}")

        unique_chunks = {lang: [] for lang in AVAILABLE_LANGUAGES}
        for source in sources:
            filename = os.path.basename(source)
            self._logging_callback(f'Starting pipeline for source {filename}...', 0)
            result = self._process_source(source)
            self._logging_callback(f'Storing chunks for {filename}...', 100, result)

            if result.chunks:
                unique_chunks[result.lang].extend(result.chunks)
        
        if all([len(chunks) == 0 for chunks in unique_chunks.values()]):
            self._logging_callback('No new data could be extracted from selected files!', 100)
            implogger.warning(f"File(s) provided for the insertion do not contain any unique information. Terminating the pipeline without importing")
            return 
        
        self._logging_callback('Importing chunks to database...', 110)
        self._import_to_database(unique_chunks)
        self._logging_callback('Successfully imported all documents!', 100)



    def import_document(self, source: Path | str):
        """
        Import a single document into the database.

        Args:
            source (Path | str): Path to the document to process and import.
        """
        self.import_many_documents([source])
     
    
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
                failures = self._wvtserv.batch_import(data_rows=chunks, lang=lang)
 

    def _process_source(self, source: Path | str) -> tuple[list, str]:
        """
        Process a single document source, deduplicate its chunks, and
        determine its language.

        Args:
            source (Path | str): Path to the document to process.

        Returns:
            tuple[list, str]: List of unique chunks and detected language.
        """
        result: ProcessingResult = self._processor.process(source)

        if not result:
            implogger.error(f"Failed to process document {source}: {result.status}")
            return [], ''
        
        unique_chunks = result.chunks
        if not self._reset_collections_on_import:
            unique_chunks = self._deduplicate(result)
        return ProcessingResult(unique_chunks, result.source, result.lang)


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
