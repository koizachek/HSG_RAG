import logging

from pathlib import Path
from ..database.weaviate.wvt_service import WeaviateService
from ..processing.processor import DataProcessor, ProcessingResult, ProcessingStatus

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ImportPipeline:
    def __init__(self) -> None:
        self._processor = DataProcessor()
        self._wvtserv   = WeaviateService()


    def import_document(self, source: Path | str):
        result: ProcessingResult = self._processor.process_document(source)

        if not result.status == ProcessingStatus.SUCCESS:
            logger.info(f"Failed to process document {source}: {result.status}")
            raise Exception("something happened")
        print(result.chunks)
        failures = self._wvtserv.batch_import(data_rows=result.chunks, lang=result.language)
        print(failures)


if __name__ == "__main__":
    pipeline = ImportPipeline()
    pipeline.import_document('hsg.pdf')
