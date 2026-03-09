from docling.document_converter import InputFormat
from docling_core.types.doc.document import DoclingDocument

from src.pipeline.processors import ProcessorBase
from src.utils.logging import get_logger

logger = get_logger('scraper.processor')

class HTMLProcessor(ProcessorBase):

    def process(self, url: str, html_content: str) -> DoclingDocument:
        if not html_content:
            logger.warning('Nothing to process, HTML body is empty!')
            return None

        logger.info(f"Analyzing page layout of URL '{url}'...")
        try:
            document = self._converter.convert_string(html_content, InputFormat.HTML).document
            document.name = url
            return document 
        except Exception as e:
            logger.error(f"Failed to analyze page layout: {e}")
            return None

