from docling.document_converter import DocumentConverter, InputFormat
from docling_core.types.doc.document import DoclingDocument

from src.pipeline.utilclasses import ProcessingResult
from src.pipeline.processors import ProcessorBase
from src.utils.lang import detect_language
from src.utils.logging import get_logger

logger = get_logger('scraper.processor')

class HTMLProcessor(ProcessorBase):
    def __init__(self):
        super().__init__()


    def process(self, url: str, html_content: str) -> dict:
        if not html_content:
            logger.warn('Nothing to process, HTML body is empty!')
            return None
       
        logger.info(f"Initiating HTML processing pipeline for URL '{url}'...")
        self._logging_callback(f'{url}: Collecting HTML body...', 20)
        try:
            logger.info('Converting HTML body to plain text...')
            document: DoclingDocument = self._converter.convert_string(html_content, InputFormat.HTML).document
        except Exception as e:
            logger.error(f"Failed to convert HTML body to plain text: {e}")
            return None
        
        self._logging_callback(f'{url}: Collecting chunks...', 40)
        collected_chunks = self._collect_chunks(document)
        extracted_text = document.export_to_markdown(
            strict_text=True, 
            image_placeholder='',
        )

        self._logging_callback(f'{url}: Preparing chunks for importing...', 60)
        prepared_chunks = self._prepare_chunks(url, extracted_text, collected_chunks)

        logger.info(f"Successfully collected {len(collected_chunks)} chunks from {url}")
        
        return {
            'result': ProcessingResult(
                source=url,
                chunks=prepared_chunks,
                lang=detect_language(extracted_text), 
            ),
            'text': extracted_text
        }
