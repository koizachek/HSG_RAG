import logging, os, json, hashlib

from enum import Enum
from urllib.parse import urlparse
from pathlib import Path
from docling_core.types.doc.document import DoclingDocument
from langdetect import detect
from dataclasses import dataclass
from transformers import AutoTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

logger = logging.getLogger(__name__)

_MAX_TOKENS = 8191
_OLLAMA_TOKENIZER = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1.5")

_HASH_FILE_PATH = os.path.join(os.path.dirname(__file__), 'hashtables.json')

def _get_hash(text: str) -> str:
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()


def _import_hashtables() -> dict:
    hashtables = dict()
    
    with open(_HASH_FILE_PATH, 'a+') as f:
        try:
            f.seek(0)
            hashtables = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode the hash file {os.path.basename(_HASH_FILE_PATH)}: {e}. New hashtables will be created.")
            hashtables['documents'] = []
            hashtables['chunks'] = []
    return hashtables


def _export_hashtables(hashtables: dict):
    """
    Export hashtable data to the JSON file.

    Args:
        hashtables (dict): Hashtable dictionary containing documents and chunks.
    """
    with open(_HASH_FILE_PATH, 'w+') as f:
        json.dump(hashtables, f)


def _is_valid_url(url: str) -> bool:
    if not urlparse(url).scheme:
        url = "http://" + url
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


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
    DUPLICATION       = 4
    INCORRECT_FORMAT  = 5
    FORBIDDEN_WEBSITE = 6

    
@dataclass
class _ChunkMetadata:
    programs: str 
    date: str 
    source: str 
    document_id: str 


@dataclass
class ProcessingResult:
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    chunks: list = None
    language: str = None
        

# TODO: Move max_tokens to config.
# TODO: Tokenizer is dependent on the chosen embedding model, which should be determined in the config.
class DataProcessor:
    """
    Handles document processing, including conversion, chunking, language detection,
    and hash-based deduplication.
    """
    def __init__(self, config: dict = None) -> None:
        """
        Initialize the DataProcessor with converter, chunker, and hashtable.

        Args:
            config (dict, optional): Configuration dictionary for processing options.
        """
        self._converter = DocumentConverter()
        self._chunker = HybridChunker(
            tokenizer=HuggingFaceTokenizer(
                tokenizer=_OLLAMA_TOKENIZER,
                max_tokens=_MAX_TOKENS
            ), 
            max_tokens=_MAX_TOKENS, 
            merge_peers=True
        )
        self._hashtables = _import_hashtables()


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
        document = self._converter.convert(source=source).document
        text = document.export_to_text()
        
        t_hash = _get_hash(text)
        if t_hash in self._hashtables['documents']:
            logger.warning(f"Source {source} has already been processed, terminating the pipeline")
            return ProcessingResult(status=ProcessingStatus.DUPLICATION)
        logger.info(f"No processing history found for source {source} with hash {t_hash}, adding to hashtables")
        
        metadata = _ChunkMetadata(
            programs=_detect_programs(text),
            source=os.path.basename(source),
            date=os.path.getctime(source),
            document_id=t_hash
        )
        prepared_chunks = self._collect_chunks(document, metadata)
        logger.info(f"Successfully collected {len(prepared_chunks)} chunks from {source}")
        
        self._update_hashtables(t_hash, [chunk['chunk_id'] for chunk in prepared_chunks])
        _export_hashtables(self._hashtables)
        return ProcessingResult(chunks=prepared_chunks, language=_detect_language(text))
    
    
    def _update_hashtables(self, document_id, chunk_ids):
        """
        Update hashtables with a new document ID and collected chunk IDs.

        Args:
            document_id (str): Hash of the processed document.
            chunk_ids (list[str]): List of chunk hashes to add.
        """
        self._hashtables['documents'].append(document_id)
        self._hashtables['chunks'].extend(chunk_ids)


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
            if c_hash in self._hashtables['chunks']:
                logger.info(f"Found duplicated chunk from {metadata.document_id} with id {c_hash}, skipping...")
                continue 
            
            prepared_chunks.append({
                'body': chunk,
                'chunk_id': c_hash,
                'document_id': metadata.document_id,
                'programs': metadata.programs,
                'date': metadata.date,
                'source': metadata.source
            })
        return prepared_chunks


if __name__ == "__main__":
    gp = GeneralProcessor()
    result = gp.process_document("emba_X5_Brochure.pdf")

    if result.status == ProcessingStatus.SUCCESS:
        for chunk in result.chunks:
            print('chunk ID:', chunk['chunk_id'])
            print(chunk['body'])

