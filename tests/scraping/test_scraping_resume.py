import os
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.scraping.scraper import Scraper
from src.scraping.types import ChunkMetadata, ScrapeManifest, UrlTimestamps


class DummyNormalizer:
    @staticmethod
    def url_to_filename(url: str) -> str:
        return url.replace('https://', '').replace('http://', '').replace('/', '_')


class DummyProcessor:
    def __init__(self):
        self.chunk_calls = []
        self.merge_calls = []

    def chunk(self, document):
        self.chunk_calls.append(document.name)
        return [{
            'text': f'chunk text for {document.name}',
            'title': f'title for {document.name}',
            'size': 42,
        }]

    def merge_chunks_by_topic(self, chunk_metadatas):
        self.merge_calls.append([chunk.source_url for chunk in chunk_metadatas])
        return list(chunk_metadatas)

    def prepare_chunks(self, url, text, chunk_metadatas):
        prepared = {'en': [], 'de': []}
        for chunk in chunk_metadatas:
            prepared.setdefault(chunk.language, []).append(chunk)
        return prepared

    def extract_title(self, document):
        return f'page title for {document.name}'

    def convert_to_txt(self, document):
        return f'extracted text for {document.name}'


class DummyCleaner:
    def __init__(self):
        self.perform_calls = []

    def perform_content_analysis(self, target_url, filename):
        self.perform_calls.append((target_url, filename))


@pytest.fixture
def scraper(tmp_path, monkeypatch):
    chunks_dir = tmp_path / 'chunks'
    temp_dir = tmp_path / 'temp_chunks'
    metadata_dir = tmp_path / 'metadata'
    urls_dir = tmp_path / 'urls'
    scraping_dir = tmp_path / 'scraping'
    extracted_text_dir = tmp_path / 'extracted'

    for path in [chunks_dir, temp_dir, metadata_dir, urls_dir, scraping_dir, extracted_text_dir]:
        path.mkdir(parents=True, exist_ok=True)

    scraper = Scraper.__new__(Scraper)
    scraper._processor = DummyProcessor()
    scraper._normalizer = DummyNormalizer()
    scraper._content_cleaner = DummyCleaner()
    scraper._url_timestamps = {}
    scraper._url_temp_timestamps = {}
    scraper._url_priorities = {}
    scraper._path = SimpleNamespace(
        CHUNKS_OUTPUT=str(chunks_dir),
        TEMP_CHUNKS_OUTPUT=str(temp_dir),
        METADATA_OUTPUT=str(metadata_dir),
        URLS_OUTPUT=str(urls_dir),
        SCRAPING_OUTPUT=str(scraping_dir),
        EXTRACTED_TEXT_OUTPUT=str(extracted_text_dir),
    )

    monkeypatch.setattr('src.scraping.scraper.detect_chunk_topic', lambda text: 'general')
    monkeypatch.setattr('src.scraping.scraper.config.paths.CHUNKS_OUTPUT', str(chunks_dir), raising=False)

    save_calls = []
    saved_results = {}

    def fake_save_results(path, filename, results, target_url=None):
        normalized_results = results
        if isinstance(results, list):
            normalized_results = list(results)
        elif isinstance(results, dict):
            normalized_results = {
                key: list(value) if isinstance(value, list) else value
                for key, value in results.items()
            }

        if filename.endswith('_merged_chunks') and isinstance(normalized_results, dict):
            previous = saved_results.get((path, filename), {})
            merged = {key: list(value) for key, value in previous.items()}
            for key, value in normalized_results.items():
                merged[key] = list(value)
            saved_results[(path, filename)] = merged
            normalized_results = [
                chunk for chunks in merged.values() for chunk in chunks
            ]

        save_calls.append({
            'path': path,
            'filename': filename,
            'target_url': target_url,
            'results': normalized_results,
            'count': len(results) if hasattr(results, '__len__') else None,
        })

    scraper._save_results = fake_save_results
    scraper._save_calls = save_calls
    return scraper


def _make_tagged_document(url: str, program: str = 'EMBA', language: str = 'en'):
    return SimpleNamespace(
        document=SimpleNamespace(name=url),
        tags=SimpleNamespace(program=program, language=language),
    )



def _make_existing_chunk(url: str, program: str = 'EMBA', language: str = 'en', chunk_id: str = 'existing_001') -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=chunk_id,
        text=f'existing chunk for {url}',
        source_url=url,
        program=program,
        language=language,
        topic='general',
        last_scraped=datetime.now(),
        page_title=f'page title for {url}',
        section_heading='existing heading',
        token_size=42,
    )



def _make_timestamp() -> UrlTimestamps:
    return UrlTimestamps(
        last_modified=None,
        last_scraped=datetime.now(),
        etag=None,
        page_hash=None,
    )


def _write_extracted_text(scraper, url: str) -> None:
    url_filename = scraper._normalizer.url_to_filename(url)
    path = os.path.join(scraper._path.EXTRACTED_TEXT_OUTPUT, url_filename + '.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'previously extracted text for {url}')


class TestTempBehaviorComplete:

    def test_collect_chunks_chunks_everything_when_temp_is_empty(self, scraper):
        target_url = 'https://target.example/'
        tagged_documents = [
            _make_tagged_document('https://target.example/page-1'),
            _make_tagged_document('https://target.example/page-2'),
        ]

        temp_filename = scraper._get_temp_chunks_filename(target_url)
        scraper._url_temp_timestamps = {
            'https://target.example/page-1': _make_timestamp(),
            'https://target.example/page-2': _make_timestamp(),
        }

        result = scraper._collect_chunks(
            tagged_documents,
            target_url=target_url,
            existing_merged_chunks={},
        )

        assert [chunk.source_url for chunk in result['merged']] == [
            'https://target.example/page-1',
            'https://target.example/page-2',
        ]
        assert scraper._processor.chunk_calls == [
            'https://target.example/page-1',
            'https://target.example/page-2',
        ]
        assert scraper._url_timestamps == {}
        assert set(scraper._pending_timestamps) == {
            'https://target.example/page-1',
            'https://target.example/page-2',
        }

        temp_snapshots = [
            [chunk.source_url for chunk in call['results']]
            for call in scraper._save_calls
            if call['path'] == scraper._path.TEMP_CHUNKS_OUTPUT and call['filename'] == temp_filename
        ]
        assert temp_snapshots == [
            ['https://target.example/page-1'],
            ['https://target.example/page-1', 'https://target.example/page-2'],
        ]

    def test_collect_chunks_rechunks_urls_already_present_in_temp(self, scraper):
        target_url = 'https://target.example/'
        existing_chunk = _make_existing_chunk('https://target.example/page-1')
        _write_extracted_text(scraper, 'https://target.example/page-1')
        tagged_documents = [
            _make_tagged_document('https://target.example/page-2'),
        ]

        temp_filename = scraper._get_temp_chunks_filename(target_url)
        scraper._url_temp_timestamps = {
            'https://target.example/page-2': _make_timestamp(),
        }

        result = scraper._collect_chunks(
            tagged_documents,
            target_url=target_url,
            existing_merged_chunks={
                'https://target.example/page-1': [existing_chunk],
            },
        )

        assert [chunk.source_url for chunk in result['merged']] == [
            'https://target.example/page-1',
            'https://target.example/page-2',
        ]
        assert scraper._processor.chunk_calls == [
            'https://target.example/page-2',
        ]

        temp_snapshots = [
            [chunk.source_url for chunk in call['results']]
            for call in scraper._save_calls
            if call['path'] == scraper._path.TEMP_CHUNKS_OUTPUT and call['filename'] == temp_filename
        ]
        assert temp_snapshots == [
            ['https://target.example/page-2']
        ]

    def test_scrape_target_finalizes_existing_temp_when_no_new_documents(self, scraper):
        target_url = 'https://target.example/'
        existing_chunk = _make_existing_chunk('https://target.example/page-1')
        _write_extracted_text(scraper, 'https://target.example/page-1')
        temp_filename = scraper._get_temp_chunks_filename(target_url)

        scraper._analyze_domain = lambda target: SimpleNamespace(urls=['https://target.example/page-1'])
        scraper._analyze_sitemap = lambda domain: SimpleNamespace(documents=[], discovered_urls=[])
        scraper._analyze_discoveries = lambda discovered, sitemap_urls, domain: SimpleNamespace(documents=[], discovered_urls=[])

        original_load_data = scraper._load_data

        def fake_load_data(path, filename):
            if path == scraper._path.TEMP_CHUNKS_OUTPUT and filename == temp_filename:
                return {'https://target.example/page-1': [existing_chunk]}
            return original_load_data(path, filename)

        scraper._load_data = fake_load_data

        collect_calls = []

        def fake_collect_chunks(tagged_documents, target_url, existing_merged_chunks=None):
            collect_calls.append({
                'tagged_documents': tagged_documents,
                'target_url': target_url,
                'existing_merged_chunks': existing_merged_chunks,
            })
            merged = [chunk for chunks in (existing_merged_chunks or {}).values() for chunk in chunks]
            return {
                'raw': [],
                'merged': merged,
                'deleted': [],
                'final': {'en': merged, 'de': []},
                'processed_sources': {'https://target.example/page-1'},
            }

        scraper._collect_chunks = fake_collect_chunks

        result = scraper.scrape_target(target_url)

        assert isinstance(result, ScrapeManifest)
        assert [chunk.source_url for chunk in result.chunks_by_language['en']] == [
            'https://target.example/page-1'
        ]
        assert result.processed_sources == ['https://target.example/page-1']
        assert len(collect_calls) == 1
        assert collect_calls[0]['tagged_documents'] == []
        assert collect_calls[0]['existing_merged_chunks'] == {'https://target.example/page-1': [existing_chunk]}
        assert scraper._content_cleaner.perform_calls == []

        saved_filenames = [call['filename'] for call in scraper._save_calls]
        assert saved_filenames.count('merged_chunk_metadata') == 1
        assert saved_filenames.count('raw_chunk_metadata') == 1
        assert saved_filenames.count('deleted_chunk_metadata') == 1

    def test_scrape_target_returns_empty_when_no_documents_and_no_temp(self, scraper):
        target_url = 'https://target.example/'
        temp_filename = scraper._get_temp_chunks_filename(target_url)

        scraper._analyze_domain = lambda target: SimpleNamespace(urls=['https://target.example/page-1'])
        scraper._analyze_sitemap = lambda domain: SimpleNamespace(documents=[], discovered_urls=[])
        scraper._analyze_discoveries = lambda discovered, sitemap_urls, domain: SimpleNamespace(documents=[], discovered_urls=[])

        original_load_data = scraper._load_data

        def fake_load_data(path, filename):
            if path == scraper._path.TEMP_CHUNKS_OUTPUT and filename == temp_filename:
                return {}
            return original_load_data(path, filename)

        scraper._load_data = fake_load_data

        def fail_collect_chunks(*args, **kwargs):
            raise AssertionError('_collect_chunks should not be called when there are no documents and no temp chunks')

        scraper._collect_chunks = fail_collect_chunks

        result = scraper.scrape_target(target_url)

        assert isinstance(result, ScrapeManifest)
        assert not result
        saved_filenames = [call['filename'] for call in scraper._save_calls]
        assert 'merged_chunk_metadata' not in saved_filenames
        assert scraper._content_cleaner.perform_calls == []

    def test_commit_scrape_persists_timestamps_and_removes_temp_files(self, scraper):
        target_url = 'https://target.example/'
        source_url = 'https://target.example/page-1'
        timestamp = _make_timestamp()
        scraper._pending_timestamps = {source_url: timestamp}

        for filename in (
            scraper._get_temp_chunks_filename(target_url),
            scraper._get_temp_timestamps_filename(target_url),
        ):
            path = os.path.join(scraper._path.TEMP_CHUNKS_OUTPUT, filename + '.json')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('{}')

        scraper.commit_scrape(ScrapeManifest(
            target_url=target_url,
            chunks_by_language={'en': [], 'de': []},
            processed_sources=[source_url],
        ))

        assert scraper._url_timestamps[source_url] == timestamp
        assert any(
            call['filename'] == 'url_timestamps'
            for call in scraper._save_calls
        )
        for filename in (
            scraper._get_temp_chunks_filename(target_url),
            scraper._get_temp_timestamps_filename(target_url),
        ):
            path = os.path.join(scraper._path.TEMP_CHUNKS_OUTPUT, filename + '.json')
            assert not os.path.exists(path)
