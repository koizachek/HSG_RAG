import json, os

from pathlib import Path
from src.utils.logging import get_logger
from src.processing.processor import DataProcessor, ProcessingResult, ProcessingStatus, WebsiteProcessor
from src.database.weavservice import WeaviateService

from config import AVAILABLE_LANGUAGES, HASH_FILE_PATH, DOCUMENTS_PATH

pipelogger = get_logger("pipeline_module")
implogger  = get_logger("import_pipeline")


def _get_all_sources(sources) -> list[str]:
    sources.remove('all')
    pipelogger.info(f"Getting all sources from the soruce directory at {DOCUMENTS_PATH}...")
    for source in os.listdir(DOCUMENTS_PATH):
        if source in sources: continue
        if source.endswith('.pdf'):
            sources.append(os.path.join(DOCUMENTS_PATH, source))
    pipelogger.info(f"Loaded {len(sources)} sources from the source directory")
    return sources


def _import_hashtables() -> dict:
    """
    Import deduplication hashtables from the JSON file.

    Returns:
        dict: Hashtable data containing document and chunk IDs.
    """
    hashtables = dict()
    
    with open(HASH_FILE_PATH, 'a+') as f:
        try:
            f.seek(0)
            pipelogger.info(f"Loading deduplication hashtable from file {HASH_FILE_PATH}")
            hashtables = json.load(f)
            pipelogger.info(f"Import pipeline loaded deduplication hashtable with {len(hashtables['documents'])} sources and {len(hashtables['chunks'])} chunks")
        except json.JSONDecodeError as e:
            pipelogger.warning(f"Failed to decode the hash file {os.path.basename(HASH_FILE_PATH)}: {e}; new hashtable will be created")
            hashtables['documents'] = []
            hashtables['chunks'] = []
    return hashtables


def _export_hashtables(hashtables: dict):
    """
    Export hashtable data to the JSON file.

    Args:
        hashtables (dict): Hashtable dictionary containing documents and chunks.
    """
    with open(HASH_FILE_PATH, 'w+') as f:
        json.dump(hashtables, f)
        pipelogger.info("Saved successfully imported chunk IDs in the hashtables")


class ImportPipeline:
    """
    Main pipeline class responsible for importing website and local documents
    into the database with deduplication and language-based organization.
    """

    def __init__(self) -> None:
        """Initialize the import pipeline with processors and hashtable data."""
        self._hashtables   = _import_hashtables()
        self._webprocessor = WebsiteProcessor()
        self._processor    = DataProcessor()
        self._wvtserv      = WeaviateService()
        self._saved_ids    = self._wvtserv._get_chunk_ids()


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
        _export_hashtables(self._hashtables)


    def import_many_documents(self, sources: list[Path | str]):
        """
        Import multiple documents by processing, deduplicating, and inserting
        unique chunks into the database.

        Args:
            sources (list[Path | str]): List of file paths or URLs to process.
        """
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
            chunks, lang = self._process_source(source)
            if chunks:
                unique_chunks[lang].extend(chunks)
        
        if not unique_chunks:
            implogger.warning(f"File(s) provided for the insertion do not contain any unique information. Terminating the pipeline without importing")
            return 

        self._import_to_database(unique_chunks)
        _export_hashtables(self._hashtables)


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
        for lang, chunks in unique_chunks.items():
            if not chunks: 
                continue

            failures = self._wvtserv.batch_import(data_rows=chunks, lang=lang)
            for failure in failures:
                chunk_id = failure['chunk_id']
                if chunk_id in self._hashtables['chunks']:
                    self._hashtables['chunks'].remove(chunk_id)


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

        if not result.status == ProcessingStatus.SUCCESS:
            implogger.error(f"Failed to process document {source}: {result.status}")
            return [], ''
        
        unique_chunks = self._deduplicate(result)
        return unique_chunks, result.language


    def _deduplicate(self, result: ProcessingResult):
        """
        Remove duplicate chunks and documents based on previously processed hashes.

        Args:
            result (ProcessingResult): The processing result containing document chunks.

        Returns:
            list[dict]: List of unique chunk dictionaries.
        """
        d_id = result.document_id
        unique_chunks = []

        implogger.info(f"Analyzing document with ID {d_id} for duplicated contents")
        if d_id in self._hashtables['documents']:
            implogger.warning(f"Document with ID {d_id} is a duplicate!")
            return unique_chunks
        
        for chunk in result.chunks:
            c_id = chunk['chunk_id']
            if c_id in self._hashtables['chunks']:
                continue 

            self._hashtables['chunks'].append(c_id)
            unique_chunks.append(chunk)

        if not unique_chunks:
            self._hashtables['documents'].append(d_id)
        
        implogger.info(f"Found {len(unique_chunks)} unique chunks out ouf {len(result.chunks)} collected chunks")
        return unique_chunks


if __name__ == "__main__":
    pipeline = ImportPipeline()
    #pipeline.import_many_documents(['data/hsg.pdf', 'data/emba_X5.pdf'])
    pipeline.scrape_website()
