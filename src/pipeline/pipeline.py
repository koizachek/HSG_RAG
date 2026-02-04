from src.pipeline.utilclasses import (
        _deduplication_callback_placeholder,
        _logging_callback_placeholder,
        ProcessingResult,
)
from src.pipeline.processors import *
from src.database.weavservice  import WeaviateService

from src.utils.logging import get_logger

from src.config import config

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
    ) -> None:
        """
        Initialize the import pipeline with optional callbacks for logging and deduplication.

        This sets up the processors for websites and documents and recieves existing chunk IDs 
        from the database for deduplication purposes.

        Args:
            logging_callback (callable, optional): A callback function for logging progress.
                Defaults to a placeholder if not provided.
            deduplication_callback (callable, optional): A callback function for handling
                deduplication decisions. Defaults to a placeholder if not provided.
        """
        self._logging_callback = logging_callback or _logging_callback_placeholder
        self._deduplication_callback = deduplication_callback or _deduplication_callback_placeholder
        self._webprocessor = WebsiteProcessor(self._logging_callback)
        self._docprocessor = DocumentProcessor(self._logging_callback)
        self._service      = WeaviateService()
        self._ids          = self._service._collect_chunk_ids()
        
        implogger.info('Import pipeline initialization finished!')
        

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
        chunks  = self._pipeline(paths, self._docprocessor, reset_collections)
        wchunks = self._pipeline(urls,  self._webprocessor, reset_collections)
        for lang in chunks.keys():
            chunks[lang].extend(wchunks[lang]) 

        if reset_collections:
            self._logging_callback('Resetting database collections...', 60)
            self._service._reset_collections()
        
        self._logging_callback('Importing chunks to database...', 90)
        for lang, ch in chunks.items():
            self._service.batch_import(data_rows=ch, lang=lang) 
        self._logging_callback('Successfully imported {sum([len(ch) for ch in chunks.values()])} chunks!', 100)


    def _pipeline(
            self, 
            sources: list[str], 
            processor: ProcessorBase,
            reset_collections: bool,
        ) -> dict:
        """
        Internal pipeline to process a list of sources using a given processor.

        Handles processing, deduplication (if not resetting), and organizes unique chunks by language.
        If no new unique data is found, logs a warning and returns empty chunks.

        Args:
            sources (list[str]): List of sources (paths or URLs) to process.
            processor (ProcessorBase): The processor instance to use for handling sources.
            reset_collections (bool): If True, skip deduplication.

        Returns:
            dict: A dictionary mapping languages to lists of unique chunk dictionaries.
        """
        unique_chunks = {lang: [] for lang in config.get('AVAILABLE_LANGUAGES')}

        if not sources:
            return unique_chunks
        
        for source in sources:
            self._logging_callback(f'Starting pipeline for {source}...', 0)
            result = processor.process(source)

            if not result.chunks:
                implogger.error(f"Failed to process {source}!")
                self._logging_callback(f"Failed to process {source}!", 100, result, failed=True)
                continue
            
            if not reset_collections:
                self._deduplicate(result)

            self._logging_callback(f'Storing chunks for {source}...', 100, result)
            unique_chunks[result.lang].extend(result.chunks)

        if all([len(chunks) == 0 for chunks in unique_chunks.values()]):
            self._logging_callback('No new data could be extracted from these sources!', 100)
            implogger.warning(f"File(s) provided for the insertion do not contain any unique information.")
        
        return unique_chunks
        

    def _deduplicate(self, result: ProcessingResult) -> ProcessingResult:
        """
        Remove duplicate chunks based on chunks that are already stored in the database.

        If all chunks are duplicates, invokes the deduplication callback to decide whether
        to delete existing duplicates and reimport. Otherwise, returns only unique chunks.

        Args:
            result (ProcessingResult): The processing result containing document chunks.

        Returns:
            list[dict]: List of unique chunk dictionaries (or all if reimporting duplicates).
        """
        self._logging_callback('Performing deduplication...', 80)
        unique_chunks = []
        duplicate_ids = []
        for chunk in result.chunks:
            chunk_id = chunk['chunk_id']
            if chunk_id in self._ids:
                duplicate_ids.append(chunk_id)
            else: 
                unique_chunks.append(chunk)
        
        implogger.info(f"Found {len(duplicate_ids)} already existing IDs in {len(result.chunks)} collected chunks")
        if duplicate_ids: 
            implogger.info(f"Duplicates found! Calling deduplication callback...")
            if self._deduplication_callback(result.source, len(duplicate_ids)):
                implogger.info('Duplicated chunks will be reimported as new...')
                self._service._delete_by_id(duplicate_ids) 
                return result
        
        result.chunks = unique_chunks
        return result
