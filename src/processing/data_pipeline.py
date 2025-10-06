import logging, os

from enum import Enum
from urllib.parse import urlparse
from pathlib import Path
from langdetect import detect
from dataclasses import dataclass
from transformers import AutoTokenizer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

logger = logging.getLogger(__name__)

_MAX_TOKENS = 8191
_OLLAMA_TOKENIZER = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1.5")


def _is_valid_url(url: str) -> bool:
    if not urlparse(url).scheme:
        url = "http://" + url
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class ProcessingStatus(Enum):
    SUCCESS            = 'success',
    FAILURE            = 'failure',
    INCORRECT_FORMAT   = 'incorrect_format',
    FORBIDDEN_WEBSITE  = 'forbidden_website'


@dataclass
class ProcessingResult:
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    data: dict = None
        

# TODO: Move max_tokens to config.
# TODO: Tokenizer is dependent on the chosen embedding model, which should be determined in the config.
class GeneralProcessor:
    def __init__(self, config: dict = None) -> None:
        self._converter = DocumentConverter()
        self._chunker = HybridChunker(
            tokenizer=HuggingFaceTokenizer(
                tokenizer=_OLLAMA_TOKENIZER,
                max_tokens=_MAX_TOKENS
            ), 
            max_tokens=_MAX_TOKENS, 
            merge_peers=True
        )


    def process_all(self, sources: list[Path | str]) -> list[ProcessingResult]:
        for source in sources:
            self.process_document(source)


    def process_document(self, source: Path | str) -> ProcessingResult:
        title = ":)"
        if os.path.exists(source) and os.path.isfile(source):
            title = os.path.basename(source)
        elif _is_valid_url(source):
            title = "internet"
        else:
            return ProcessingResult(status=INCORRECT_FORMAT)
        
        logger.info(f"Initiating processing pipeline for document titled '{title}' under '{source}'.")
        document = self._converter.convert(source=source).document
        
        # Concatenate the document title to the beginning of each chunk.
        # This provides additional context.
        chunks = self._chunker.chunk(document)
        chunks = [f"{title} {self._chunker.contextualize(chunk=chunk)}" for chunk in chunks]
        
        text = document.export_to_text()
        print(self._detect_language(text))
        print(self._get_programms(text))

        for chunk in chunks:
            print(chunk, end='\n\n')

        return ProcessingResult(data={'title': title, 'body': chunks})

    
    def _detect_language(self, text: str):
        return 'de' if detect(text) == 'de' else 'en'


    def _get_programms(self, text: str):
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


if __name__ == "__main__":
    gp = GeneralProcessor()

    gp.process_document("google.com")
