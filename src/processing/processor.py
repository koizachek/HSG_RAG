import os, re, hashlib, time, json
import importlib.util 

from enum import Enum
from pathlib import Path
from dataclasses import dataclass
from transformers import AutoTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from docling_core.types.doc.document import DoclingDocument

from src.utils.lang import detect_language
from src.utils.logging import get_logger
from config import BASE_URL, CHUNK_MAX_TOKENS, WeaviateConfiguration as wvtconf

weblogger  = get_logger("website_processor")
datalogger = get_logger("data_processor")

_TRANSFORMERS_TOKENIZER = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
_EN_URL_PATTERN = r'\[EN\]\((https://emba\.unisg\.ch/en/[^\s)]+)\)'
_PROGRAM_URL_PATTERN = r'https://emba\.unisg\.ch/(?:programm[^\s)]+|en/embax)'


def _get_en_version(text: str):
    """Extract the English version URL from the given text, if available."""
    result = re.search(_EN_URL_PATTERN, text)
    if result:
        return result.group(1)
    return ""


def _get_program_urls(text: str):
    """Find all program URLs in the given text."""
    return re.findall(_PROGRAM_URL_PATTERN, text)


class ProcessingStatus(Enum):
    NOT_FOUND         = 1
    SUCCESS           = 2
    FAILURE           = 3
    INCORRECT_FORMAT  = 5


@dataclass
class ProcessingResult:
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    chunks: list = None
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
        self._strategies = self._load_strategies()


    def _load_strategies(self):
        properties = {}
        strategies = {}
        
        os.makedirs(wvtconf.PROPERTIES_PATH, exist_ok=True)
        os.makedirs(wvtconf.STRATEGIES_PATH, exist_ok=True)
        properties_path = os.path.join(wvtconf.PROPERTIES_PATH, 'properties.json')
        if not os.path.exists(properties_path):
            raise ValueError(f"Properties file does not exist under {properties_path}! Ensure that the database interface was opened at least once!")

        with open(properties_path) as f:
            properties = json.load(f)

        for prop in properties.keys():
            strat_file = f'strat_{prop}.py'
            strat_path = os.path.join(wvtconf.STRATEGIES_PATH, strat_file)
            if not os.path.exists(strat_path):
                raise ValueError(f"Could not find strategy for property {prop}!")

            spec = importlib.util.spec_from_file_location(
                name=prop,
                location=strat_path
            )
            strategy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(strategy)

            if not hasattr(strategy, 'run'):
                raise ValueError(f"Strategy '{strat_file}' has no 'run' function!")

            strategies[prop] = strategy

        return strategies
        

    def process(self):
        """Abstract method to be implemented by subclasses."""
        raise NotImplementedError("This method is not implemented in ProcessorBase")

    
    def _prepare_chunks(self, document_name: str, document_content: str, chunks: list[str]) -> list[dict]:
        prepared_chunks = []
        for chunk in chunks:
            prepared_chunk = {}
            for prop, strat in self._strategies.items():
                prepared_chunk[prop] = strat.run(document_name, document_content, chunk)
            prepared_chunks.append(prepared_chunk)

        return prepared_chunks


    def _collect_chunks(self, document: DoclingDocument) -> list[str]:
        """
        Collect text chunks from a document and prepare them with metadata.

        Args:
            document (DoclingDocument): The converted document object.
            metadata (_ChunkMetadata): Metadata containing program, source, and date information.

        Returns:
            list[dict]: List of chunk dictionaries containing text and metadata.
        """
        collected_chunks = [self._chunker.contextualize(chunk=c) for c in self._chunker.chunk(document)]
        return collected_chunks


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
                weblogger.info(f"Found following program URLs: {', '.join(program_urls)}.")

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
        
        document_name = url
        document_content = document.export_to_markdown()
        collected_chunks = self._collect_chunks(document)
        del collected_chunks[0]
        
        prepared_chunks = self._prepare_chunks(document_name, document_content, collected_chunks)
        
        weblogger.info(f"Successfully collected {len(prepared_chunks)} chunks from {url}")
        
        return ProcessingResult(
            chunks=collected_chunks, 
            language=detect_language(document_content), 
        )


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
        
        document_name = os.path.basename(source)
        document_content = document.export_to_markdown()
        collected_chunks = self._collect_chunks(document)

        prepared_chunks = self._prepare_chunks(document_name, document_content, collected_chunks)

        datalogger.info(f"Successfully collected {len(prepared_chunks)} chunks from {document_name}")

        return ProcessingResult(
            chunks=prepared_chunks, 
            language=detect_language(document_content), 
        )


if __name__ == "__main__":
    processor = WebsiteProcessor()
    results = processor.process()

    for result in results:
        for chunk in result.chunks:
            print(chunk['body'], end='\n\n')
