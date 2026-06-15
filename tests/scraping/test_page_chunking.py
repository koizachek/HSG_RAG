import pytest, os

from src.scraping.html_processor import HTMLProcessor
from src.scraping.content_cleaner import ContentCleaner
from src.utils.logging import init_logging
from src.config import config

class TestPageChunking:

    def test_chunking_pipeline(self):
        init_logging()

        html_path = config.paths.RAW_HTML_OUTPUT
        required_fixtures = [
            os.path.join(html_path, 'embax-ch.html'),
            os.path.join(html_path, 'embax-ch_admissions_student-profile.html'),
            # Tests for tables and lists
            os.path.join(html_path, 'embax-ch_admissions_deadlines-fees.html'),
            os.path.join(html_path, 'embax-ch_events.html')
        ]
        missing = [path for path in required_fixtures if not os.path.exists(path)]
        if missing:
            # Integration test over local scrape artifacts (data/* is not in
            # git). Skip instead of failing on machines without a prior scrape.
            pytest.skip(
                "Requires scraped raw HTML in data/raw_html "
                f"(missing: {', '.join(os.path.basename(p) for p in missing)}). "
                "Run a scrape of embax.ch first."
            )

        processor = HTMLProcessor()
        cleaner   = ContentCleaner(full_scraping=True)
        raw_texts = []
        documents = []

        for raw_html_file_path in required_fixtures:
            raw_html = open(raw_html_file_path, 'r', encoding='utf-8').read()
            cleaned_html = cleaner.clean_mobile_content(raw_html)
            document = processor.process(url='https://embax.ch', html_content=cleaned_html)
            
            raw_text = processor.convert_to_txt(document)
            assert len(raw_text) > 100
            raw_texts.append(raw_text) 

            cleaner.collect_repetitive_content(document)
            documents.append(document)
        
        cleaner.perform_content_analysis()
        for document, raw_text in zip(documents, raw_texts):
            print()
            cleaner.clean_document(document)
            cleaned_text = processor.convert_to_txt(document)

            assert len(cleaned_text) > 100 
            assert raw_text != cleaned_text
            assert len(cleaned_text) < len(raw_text)

            chunks = processor.chunk(document)
            assert chunks
            for _, chunk in enumerate(chunks, start=1):
                print(chunk['text'])
     

if __name__ == "__main__":
    pytest.main([__file__, '-v', '-s']) 
