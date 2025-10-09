import logging, json, os

from pathlib import Path
from ..database.weaviate.wvt_service import WeaviateService
from ..processing.processor import DataProcessor, ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_HASH_FILE_PATH = os.path.join(os.path.dirname(__file__), 'hashtables.json')

def _import_hashtables() -> dict:
    hashtables = dict()
    
    with open(_HASH_FILE_PATH, 'a+') as f:
        try:
            f.seek(0)
            logger.info(f"Loading deduplication hashtables from file {_HASH_FILE_PATH}")
            hashtables = json.load(f)
            logger.info(f"Import pipeline loaded deduplication hashtables with {len(hashtables['documents'])} saved documents and {len(hashtables['chunks'])} saved chunks")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode the hash file {os.path.basename(_HASH_FILE_PATH)}: {e}. New hashtables will be created.")
            hashtables['documents'] = []
            hashtables['chunks'] = []
    return hashtables


def _export_hashtables(hashtables: dict):
    """
    Export hashtable data to the JSON file.

    Args:
        hashtables (dict): Hashtable dictionary containing documents and chunks.
    """
    with open(_HASH_FILE_PATH, 'w+') as f:
        json.dump(hashtables, f)


class ImportPipeline:
    def __init__(self) -> None:
        self._hashtables = _import_hashtables()
        self._hashtables_copy = None
        self._processor  = DataProcessor()
        self._wvtserv    = WeaviateService()


    def import_document(self, source: Path | str):
        result: ProcessingResult = self._processor.process_document(source)

        if not result.status == ProcessingStatus.SUCCESS:
            logger.error(f"Failed to process document {source}: {result.status}")
            return
        
        self._save_hashtables()
        unique_chunks = self._deduplicate(result)
        
        if not unique_chunks:
            logger.warning(f"Found 0 unique chunks in document {source}, terminating the import")
            return

        failures = self._wvtserv.batch_import(data_rows=unique_chunks, lang=result.language)
        print(failures)
        
        _export_hashtables(self._hashtables)


    def _restore_hashtables(self):
        self._hashtables = self._hashtables_copy.copy()


    def _save_hashtables(self):
        self._hashtables_copy = self._hashtables.copy()


    def _deduplicate(self, result: ProcessingResult):
        d_id = result.document_id
        unique_chunks = []

        logger.info(f"Analyzing document with ID {d_id} for duplicated contents")
        if d_id in self._hashtables['documents']:
            return unique_chunks
        
        for chunk in result.chunks:
            c_id = chunk['chunk_id']
            if c_id in self._hashtables['chunks']:
                continue 

            self._hashtables['chunks'].append(c_id)
            unique_chunks.append(chunk)

        if not unique_chunks:
            self._hashtables['documents'].append(d_id)
        
        logger.info(f"Found {len(unique_chunks)} unique chunks out ouf {len(result.chunks)} collected chunks")
        return unique_chunks


if __name__ == "__main__":
    pipeline = ImportPipeline()
    pipeline.import_document('hsg.pdf')
