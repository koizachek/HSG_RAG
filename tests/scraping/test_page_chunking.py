import pytest, os

from src.scraping.html_processor import HTMLProcessor
from src.scraping.content_cleaner import ContentCleaner
from src.utils.logging import init_logging
from src.config import config

class TestPageChunking:

    def testChunkingPipeline(self):
        init_logging()
        
        processor = HTMLProcessor()
        cleaner   = ContentCleaner()
        raw_texts = []
        documents = []
        
        html_path = config.paths.RAW_HTML_OUTPUT
        for raw_html_file_path in [
            os.path.join(html_path, 'embax-ch.html'),
            os.path.join(html_path, 'embax-ch_admissions.html'),
            # Tests for tables and lists
            os.path.join(html_path, 'embax-ch_admissions_deadlines-fees.html')
        ]:
            raw_html = open(raw_html_file_path, 'r').read()
            document = processor.process(url='https://embax.ch', html_content=raw_html)
            
            raw_text = processor.convert_to_txt(document)
            assert len(raw_text) > 100
            raw_texts.append(raw_text) 

            cleaner.collect_repetitive_content(document)
            documents.append(document)
        
        cleaner.perform_content_analysis()
        for document, raw_text in zip(documents, raw_texts):
            cleaner.clean_document(document)
            cleaned_text = processor.convert_to_txt(document)

            assert len(cleaned_text) > 100 
            assert raw_text != cleaned_text
            assert len(cleaned_text) < len(raw_text)

            chunks = processor.chunk(document)
            assert chunks
            for _, chunk in enumerate(chunks, start=1):
                assert len(chunk['text']) > 50


if __name__ == "__main__":
    pytest.main([__file__, '-v', '-s']) 
