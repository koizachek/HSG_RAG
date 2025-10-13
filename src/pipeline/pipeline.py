import json, os

from pathlib import Path
from src.utils.logging import init_logging, get_logger
from src.processing.processor import DataProcessor, ProcessingResult, ProcessingStatus, WebsiteProcessor
from src.database.weaviate import WeaviateService

from config import AVAILABLE_LANGUAGES, HASH_FILE_PATH

init_logging(interactive_mode=False)
pipelogger = get_logger("pipeline_module")
implogger  = get_logger("import_pipeline")

def _import_hashtables() -> dict:
    hashtables = dict()
    
    with open(HASH_FILE_PATH, 'a+') as f:
        try:
            f.seek(0)
            pipelogger.info(f"Loading deduplication hashtables from file {HASH_FILE_PATH}")
            hashtables = json.load(f)
            pipelogger.info(f"Import pipeline loaded deduplication hashtables with {len(hashtables['documents'])} saved documents and {len(hashtables['chunks'])} saved chunks")
        except json.JSONDecodeError as e:
            pipelogger.warning(f"Failed to decode the hash file {os.path.basename(HASH_FILE_PATH)}: {e}. New hashtables will be created.")
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
    def __init__(self) -> None:
        self._hashtables   = _import_hashtables()
        self._webprocessor = WebsiteProcessor()
        self._processor    = DataProcessor()
        self._wvtserv      = WeaviateService()


    def scrape_website(self):
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
        unique_chunks = {lang: [] for lang in AVAILABLE_LANGUAGES}
        for source in sources:
            chunks, lang = self._process_source(source)
            if chunks:
                unique_chunks[lang].extend(chunks)
        
        if not unique_chunks:
            implogger.warning(f"File(s) provided for the insertion do not contain any unique information. Terminating the pipeline without importing")
            return 

        # TODO: add import retry functionality
        self._import_to_database(unique_chunks)
        _export_hashtables(self._hashtables)


    def import_document(self, source: Path | str):
        self.import_many_documents([source])
     
    
    def _import_to_database(self, unique_chunks):
        for lang, chunks in unique_chunks.items():
            if not chunks: continue

            failures = self._wvtserv.batch_import(data_rows=chunks, lang=lang)
            for failure in failures:
                chunk_id = failure['chunk_id']
                if chunk_id in self._hashtables['chunks']:
                    self._hashtables['chunks'].remove(chunk_id)


    def _process_source(self, source: Path | str) -> tuple[list, str]:
        result: ProcessingResult = self._processor.process(source)

        if not result.status == ProcessingStatus.SUCCESS:
            implogger.error(f"Failed to process document {source}: {result.status}")
            return [], ''
        
        unique_chunks = self._deduplicate(result)
        return unique_chunks, result.language


    def _deduplicate(self, result: ProcessingResult):
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
    pipeline.import_many_documents(['data/hsg.pdf', 'data/emba_X5.pdf'])
    #pipeline.scrape_website()
