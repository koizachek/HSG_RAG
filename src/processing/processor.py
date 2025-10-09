import logging, os, json, hashlib

from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from docling_core.types.doc.document import DoclingDocument
from langdetect import detect
from dataclasses import dataclass
from transformers import AutoTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

from src.scraper.scraper import Scraper
from src.processing.scraping import ScrapingProcessor
from config import BASE_URL, CHUNK_MAX_TOKENS, PROCESSED_DATA_PATH

logger = logging.getLogger(__name__)

_OLLAMA_TOKENIZER = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1.5")


def _get_hash(text: str) -> str:
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()


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
    FORBIDDEN_WEBSITE = 6

    
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
                tokenizer=_OLLAMA_TOKENIZER,
                max_tokens=CHUNK_MAX_TOKENS
            ), 
            max_tokens=CHUNK_MAX_TOKENS, 
            merge_peers=True
        )
    
    def _collect_metadata(self, document: DoclingDocument) -> _ChunkMetadata:
        text = document.export_to_text()
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
        self._scraper = Scraper()
        self._sprocessor = ScrapingProcessor()


    def scrape(self):
        self._scraper.run()
        self._sprocessor.run()
        
        self._prepare_data()
 
    
    def _prepare_data(self):
        data = json.loads(PROCESSED_DATA_PATH)


    def _process_page(self, url: str) -> ProcessingResult:
        logger.info(f"Initiating processing pipeline for url {url}")
        document = self._converter.convert(url).document
        metadata = self._collect_metadata(document)
        metadata.source = url
        collected_chunks = self._collect_chunks(document, metadata)
        
        for chunk in collected_chunks:
            print(chunk['body'], end='\n\n')

        return None


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
        return [self.process_document(source) for source in sources]


    def process_document(self, source: Path | str) -> ProcessingResult:
        """
        Process a single document source, converting it to text, chunking, and hashing.

        Args:
            source (Path | str): Path to the document to process.

        Returns:
            ProcessingResult: The result of the processing operation, including chunks and language.
        """
        if not os.path.exists(source) or not os.path.isfile(source):
            logger.error(f"Failed to initiate processing pipeline for source {source}: file does not exist")
            return ProcessingResult(status=ProcessingStatus.NOT_FOUND)
        
        logger.info(f"Initiating processing pipeline for source {source}")
        document = self._converter.convert(source).document
        metadata = self._collect_metadata(document)
        metadata.source = os.path.basename(source)
        prepared_chunks = self._collect_chunks(document, metadata)
        logger.info(f"Successfully collected {len(prepared_chunks)} chunks from {source}")
        
        return ProcessingResult(chunks=prepared_chunks, language=metadata.language, document_id=metadata.document_id)
    

if __name__ == "__main__":
    sp = WebsiteProcessor()
    result = sp.scrape()

    if result.status == ProcessingStatus.SUCCESS:
        for chunk in result.chunks:
            print('chunk ID:', chunk['chunk_id'])
            print(chunk['body'])

