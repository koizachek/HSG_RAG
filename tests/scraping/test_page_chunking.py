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
        
        for raw_html_file_path in [
            os.path.join(config.paths.RAW_HTML_OUTPUT, 'embax-ch.html'),
            os.path.join(config.paths.RAW_HTML_OUTPUT, 'embax-ch_admissions.html')
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
            for i, chunk in enumerate(chunks, start=1):
                assert len(chunk['text']) > 50
                assert chunk['size'] in range(500, 1000)
                # print(f"chunk {i}\n{chunk}", end='\n\n')


if __name__ == "__main__":
    pytest.main([__file__, '-v', '-s']) 
