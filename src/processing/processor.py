import os, re, hashlib, time

from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from langdetect import detect
from dataclasses import dataclass
from transformers import AutoTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from docling_core.types.doc.document import DoclingDocument

from src.utils.logging import get_logger
from config import BASE_URL, CHUNK_MAX_TOKENS

weblogger  = get_logger("website_processor")
datalogger = get_logger("data_processor")

_TRANSFORMERS_TOKENIZER = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
_EN_URL_PATTERN = r'\[EN\]\((https://emba\.unisg\.ch/en/[^\s)]+)\)'
_PROGRAM_URL_PATTERN = r'https://emba\.unisg\.ch/(?:programm[^\s)]+|en/embax)'


def _get_hash(text: str) -> str:
    """Generate an MD5 hash for the given text."""
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()


def _get_en_version(text: str):
    """Extract the English version URL from the given text, if available."""
    result = re.search(_EN_URL_PATTERN, text)
    if result:
        return result.group(1)
    return ""


def _get_program_urls(text: str):
    """Find all program URLs in the given text."""
    return re.findall(_PROGRAM_URL_PATTERN, text)


def _detect_language(text: str):
    """
    Detect the language of the given text.

    Args:
        text (str): The text to analyze.

    Returns:
        str: Detected language code ('de' or 'en').
    """
    return 'de' if detect(text) == 'de' else 'en'


def _detect_programs(text: str):
    """
    Identify MBA program names mentioned in the given text.

    Args:
        text (str): The text to search for program mentions.

    Returns:
        list[str]: List of detected program identifiers.
    """
    programms = []
    lc_text = text.lower()
    found = lambda txt: txt in lc_text
    
    if found('emba') or found('executive mba'):
        programms.append('emba')

    if found('iemba') or found('international emba') or found('international executive mba'):
        programms.append('iemba')

    if found('emba x'):
        programms.append('emba_x')

    return programms


class ProcessingStatus(Enum):
    NOT_FOUND         = 1
    SUCCESS           = 2
    FAILURE           = 3
    INCORRECT_FORMAT  = 5

    
@dataclass
class _ChunkMetadata:
    programs: str 
    date: str 
    document_id: str 
    language: str
    source: str = None


@dataclass
class ProcessingResult:
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    chunks: list = None
    document_id: str = None
    language: str = None
        

class _ProcessorBase:
    def __init__(self):
        """
        Initialize the Processor with converter, chunker, and hashtable.

        Args:
            config (dict, optional): Configuration dictionary for processing options.
        """
        self._converter = DocumentConverter()
        self._chunker = HybridChunker(
            tokenizer=HuggingFaceTokenizer(
                tokenizer=_TRANSFORMERS_TOKENIZER,
                max_tokens=CHUNK_MAX_TOKENS
            ), 
            max_tokens=CHUNK_MAX_TOKENS, 
            merge_peers=True
        )
    
    def process(self):
        """Abstract method to be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented in ProcessorBase")


    def _collect_metadata(self, text: str) -> _ChunkMetadata:
        """Collect metadata such as programs, date, language, and document hash."""
        return _ChunkMetadata(
                programs=_detect_programs(text),
                date=datetime.now().replace(tzinfo=timezone.utc),
                language=_detect_language(text),
                document_id=_get_hash(text))


    def _collect_chunks(self, document: DoclingDocument, metadata: _ChunkMetadata) -> list:
        """
        Collect text chunks from a document and prepare them with metadata.

        Args:
            document (DoclingDocument): The converted document object.
            metadata (_ChunkMetadata): Metadata containing program, source, and date information.

        Returns:
            list[dict]: List of chunk dictionaries containing text and metadata.
        """
        chunks = [self._chunker.contextualize(chunk=c) for c in self._chunker.chunk(document)]
        prepared_chunks = []
        for chunk in chunks:
            c_hash = _get_hash(chunk)            
            prepared_chunks.append({
                'body': chunk,
                'chunk_id': c_hash,
                'document_id': metadata.document_id,
                'programs': metadata.programs,
                'date': metadata.date,
                'source': metadata.source
            })
        return prepared_chunks


class WebsiteProcessor(_ProcessorBase):
    def __init__(self):
        """Initialize the WebsiteProcessor with base processing capabilities."""
        super().__init__()


    def process(self) -> list[ProcessingResult]:
        """
        Scrape and process program pages from the HSG website.

        Returns:
            list[ProcessingResult]: A list of processing results for each processed URL.
        """
        weblogger.info("Initiating scraping and processing of the HSG program pages.")
        urls = [BASE_URL]
        results = []
        while urls:
            url = urls.pop()
            result, text = self._process_url(url)

            if result.status != ProcessingStatus.SUCCESS:
                weblogger.warning(f"Failed to process URLs {url}.")
                continue 

            if url == BASE_URL:
                program_urls = _get_program_urls(text)
                urls.extend(program_urls)
                weblogger.info(f"Found following program URLs: {program_urls}.")

            if '/en/' not in url:
                en_url = _get_en_version(text)
                urls.append(en_url)
                weblogger.info(f"Added an english version of the URL {en_url} to the processing list")
            
            results.append(result)
            time.sleep(2)

        weblogger.info(f"Successfully processed {len(results)} URLs.")
        return results 
    

    def _process_url(self, url: str) -> tuple[ProcessingResult, str]:
        """
        Process the content of a single URL, converting it into chunks with metadata.

        Args:
            url (str): The URL of the webpage to process.

        Returns:
            tuple[ProcessingResult, str]: The processing result and the extracted text.
        """
        weblogger.info(f"Initiating processing pipeline for url {url}")
        try:
            document = self._converter.convert(url).document
        except Exception as e:
            weblogger.error(f"Failed to load the contents of the url page {url}: {e}")
            return ProcessingResult(status=ProcessingStatus.FAILURE)
        
        text = document.export_to_text()
        metadata = self._collect_metadata(text)
        metadata.source = url
        collected_chunks = self._collect_chunks(document, metadata)
        del collected_chunks[0]
        weblogger.info(f"Successfully collected {len(collected_chunks)} chunks from {url}")
        
        return ProcessingResult(chunks=collected_chunks, language=metadata.language, document_id=metadata.document_id), text


class DataProcessor(_ProcessorBase):
    """
    Handles document processing, including conversion, chunking, language detection,
    and hash-based deduplication.
    """

    def process_many_documents(self, sources: list[Path | str]) -> list[ProcessingResult]:
        """
        Process a list of document sources sequentially.

        Args:
            sources (list[Path | str]): List of file paths or URLs to process.

        Returns:
            list[ProcessingResult]: List of results for each processed document.
        """
        return [self.process(source) for source in sources]


    def process(self, source: Path | str) -> ProcessingResult:
        """
        Process a single document source, converting it to text, chunking, and hashing.

        Args:
            source (Path | str): Path to the document to process.

        Returns:
            ProcessingResult: The result of the processing operation, including chunks and language.
        """
        if not os.path.exists(source) or not os.path.isfile(source):
            datalogger.error(f"Failed to initiate processing pipeline for source {source}: file does not exist")
            return ProcessingResult(status=ProcessingStatus.NOT_FOUND)
        
        datalogger.info(f"Initiating processing pipeline for source {source}")
        document = self._converter.convert(source).document
        metadata = self._collect_metadata(document.export_to_text())
        metadata.source = os.path.basename(source)
        collected_chunks = self._collect_chunks(document, metadata)
        datalogger.info(f"Successfully collected {len(collected_chunks)} chunks from {source}")
 
        return ProcessingResult(chunks=collected_chunks, language=metadata.language, document_id=metadata.document_id)


if __name__ == "__main__":
    processor = WebsiteProcessor()
    results = processor.process()

    for result in results:
        for chunk in result.chunks:
            print(chunk['body'], end='\n\n')
