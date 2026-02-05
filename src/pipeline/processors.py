from collections import defaultdict
import os, re, time, json
import importlib.util 

from pathlib import Path
from transformers import AutoTokenizer

from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from docling.datamodel.pipeline_options import (
        PdfPipelineOptions, 
        RapidOcrOptions,
        LayoutOptions,
)
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
from docling.document_converter import DocumentConverter, PdfFormatOption, InputFormat
from docling.chunking import HybridChunker
from docling_core.types.doc.document import DoclingDocument

from src.pipeline.utilclasses import ProcessingResult
from src.utils.lang import detect_language
from src.utils.logging import get_logger
from config import CHUNK_MAX_TOKENS, WeaviateConfiguration as wvtconf

weblogger  = get_logger("website_processor")
datalogger = get_logger("data_processor")

class ProcessorBase:
    def __init__(self, logging_callback) -> None:
        """
        Initialize the base processor with document conversion and chunking tools.

        Sets up the PDF pipeline options, document converter, tokenizer, and chunker.
        Loads strategies for chunk preparation.

        Args:
            logging_callback (callable): A callback function for logging progress.
        """
        pipeline_options = PdfPipelineOptions(
            do_ocr=True,
            ocr_options=RapidOcrOptions(
                force_full_page_ocr=True,
            ),
            generate_page_images=False,
            images_scale=3.0,
            do_layout_analysis=True,
            do_table_structure=True,
            do_cell_matching=True,
            layout_options=LayoutOptions(
                model_spec={
                    "name": "docling_layout_egret_medium",  
                    "repo_id": "docling-project/docling-layout-egret-medium",
                    "revision": "main",
                    "model_path": "",
                    "supported_devices": ["cuda"]  
                },
                create_orphan_clusters=True,  
                keep_empty_clusters=False,
                skip_cell_assignment=False,
            ),
        )
        self._converter: DocumentConverter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            },
        )
        tokenizer = AutoTokenizer.from_pretrained("nomic-ai/nomic-embed-text-v1.5")
        self._chunker = HybridChunker(
            tokenizer=HuggingFaceTokenizer(
                tokenizer=tokenizer,
                max_tokens=CHUNK_MAX_TOKENS
            ), 
            max_tokens=CHUNK_MAX_TOKENS, 
            merge_peers=True
        )
        self._strategies = self._load_strategies()
        self._logging_callback = logging_callback
        
    
    def _load_strategies(self):
        """
        Load strategies for processing document properties from configured paths.

        Creates necessary directories if they don't exist, loads properties from JSON,
        and dynamically imports strategy modules for each property.

        Returns:
            dict: A dictionary mapping property names to their strategy modules.

        Raises:
            ValueError: If properties file or strategy files are missing, or if a strategy lacks a 'run' function.
        """
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
        """
        Abstract method to be implemented by subclasses for processing sources.

        Raises:
            NotImplementedError: If not overridden in a subclass.
        """
        raise NotImplementedError("This method is not implemented in ProcessorBase")


    def _prepare_chunks(self, document_name: str, document_content: str, chunks: list[str]) -> list[dict]:
        """
        Prepare chunks by applying strategies to generate properties for each chunk.

        Args:
            document_name (str): The name or identifier of the document.
            document_content (str): The full content of the document.
            chunks (list[str]): List of text chunks to prepare.

        Returns:
            list[dict]: List of dictionaries, each containing properties for a chunk.
        """
        prepared_chunks = []
        for chunk in chunks:
            prepared_chunk = {}
            for prop, strat in self._strategies.items():
                prepared_chunk[prop] = strat.run(document_name, document_content, chunk)
            prepared_chunks.append(prepared_chunk)

        return prepared_chunks
    

    def _clean_content(self, document_content: str) -> str:
        """
        Clean the document content by removing garbage symbols and normalizing whitespace.

        Handles specific replacements for punctuation, symbols, and line breaks.

        Args:
            document_content (str): The raw document content to clean.

        Returns:
            str: The cleaned document content.
        """
        cleaned = re.sub(r'\s+/\s+', '/', document_content)           
        cleaned = re.sub(r'\s+\.\s+', '.', cleaned)          
        cleaned = re.sub(r',\s+', '.', cleaned)              
        cleaned = re.sub(r'\s+\|\s+', ' ', cleaned)
        cleaned = re.sub(r'\/\s+', '/', cleaned)
        cleaned = re.sub(r'\s+/','/', cleaned)
        cleaned = re.sub(r'\s+\.', '.', cleaned)
        cleaned = re.sub(r'(\d+)\s*,\s*(\d{4})', r'\1', cleaned)   
        cleaned = re.sub(r'(\d+)\s*/\s*(\d+)', r'\1', cleaned)
        cleaned = re.sub(r'\.(\d{4})', r'.\1', cleaned)
        
        cleaned = cleaned.replace('ä', 'ä').replace('ö', 'ö').replace('ü', 'ü')

        cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)
        cleaned = re.sub(r' +', ' ', cleaned)

        return cleaned


    def _extract_document_content(self, document: DoclingDocument) -> str:
        """
        Extract and compile text content from the document into a single string.

        Organizes text items by page, sorts them by position, and joins them
        while handling line breaks and spacing.

        Args:
            document (DoclingDocument): The document object to extract content from.

        Returns:
            str: The cleaned, compiled text content.
        """
        page_texts = defaultdict(list)
        for text_item in document.texts:
            if not text_item.text.strip():
                continue 

            prov = text_item.prov[0] if text_item.prov else None 
            if prov:
                page_number = prov.page_no 
                bbox = prov.bbox 
                page_texts[page_number].append({
                    'text': text_item.text.strip(),
                    'top': bbox.t,
                    'left': bbox.l,
                    'bottom': bbox.b,
                })

        full_page_texts = []
        for page_number in sorted(page_texts.keys()):
            text_items = sorted(
                page_texts[page_number], 
                key=lambda text: (-text['top'], text['left']),
            )

            content = []
            last_bottom = None 

            line_treshold = 15

            for item in text_items:
                text = item['text']
                
                if last_bottom is not None and (last_bottom - item['bottom'] > line_treshold):
                    if content:
                        full_page_texts.append(' '.join(content))
                        content = []

                    if last_bottom - item['bottom'] > 50:
                        full_page_texts.append("")

                content.append(text)
                last_bottom = item['bottom']
            
            if content:
                full_page_texts.append(' '.join(content))

        full_text = '\n\n'.join(full_page_texts)
        cleaned_text = self._clean_content(full_text)
        
        return cleaned_text
     

    def _collect_chunks(self, document: DoclingDocument) -> list[str]:
        """
        Collect contextualized chunks from the document using the chunker.

        Args:
            document (DoclingDocument): The document to chunk.

        Returns:
            list[str]: List of enriched text chunks.
        """
        chunks = []
        for base_chunk in self._chunker.chunk(dl_doc=document):
            enriched = self._chunker.contextualize(chunk=base_chunk)
            chunks.append(enriched)
        return chunks


    def _collect_chunks_fallback(self, document_content: str) -> list[str]:
        """
        Fallback method to chunk the document content manually using tokenization.

        Splits the content into overlapping chunks based on token limits.

        Args:
            document_content (str): The full content extracted from document.

        Returns:
            list[str]: List of text chunks.
        """ 
        tokenizer_wrapper = self._chunker.tokenizer
        tokenizer = getattr(tokenizer_wrapper, 'tokenizer', tokenizer_wrapper)

        tokens = tokenizer.encode(document_content)
        chunk_size = self._chunker.max_tokens
        overlap = 50
        
        collected_chunks = []
        for i in range(0, len(tokens), chunk_size-overlap):
            chunk_tokens = tokens[i:i+chunk_size]
            chunk = tokenizer.decode(
                chunk_tokens, 
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True
            )
            collected_chunks.append(chunk)

        return collected_chunks
 

class DocumentProcessor(ProcessorBase):
    def process(self, source: Path | str) -> ProcessingResult:
        """
        Process a single local document, converting it to text, chunking, and preparing for import.

        Handles document conversion, chunk collection (with fallback if needed),
        chunk preparation, and language detection.

        Args:
            source (Path | str): Path to the document to process.

        Returns:
            ProcessingResult: The result containing chunks, source name, and detected language.
            Returns None if the source does not exist or processing fails.
        """
        if not os.path.exists(source) or not os.path.isfile(source):
            datalogger.error(f"Failed to initiate processing pipeline for source {source}: file does not exist")
            return ProcessingResult(source=source, chunks=None, lang='')
        
        document_name = os.path.basename(source) 
        datalogger.info(f"Initiating processing pipeline for source {document_name}")
        self._logging_callback(f'Converting source {document_name}...', 20)
        document = self._converter.convert(source).document
        
        self._logging_callback(f'Collecting chunks from {document_name}...', 40)
        collected_chunks = self._collect_chunks(document)
        document_content = MarkdownDocSerializer(doc=document).serialize().text

        if len(collected_chunks) <= 1: # Document content manual extraction 
            document_content = self._extract_document_content(document)
            document = self._converter.convert_string(
                content=document_content, 
                format=InputFormat.MD
            ).document
            collected_chunks = self._collect_chunks(document)
        
        self._logging_callback(f'Preparing chunks for {document_name} for importing...', 60)
        prepared_chunks = self._prepare_chunks(document_name, document_content, collected_chunks)

        datalogger.info(f"Successfully collected {len(prepared_chunks)} chunks from {document_name}")

        return ProcessingResult(
            chunks=prepared_chunks,
            source=document_name,
            lang=detect_language(document_content), 
        )


class WebsiteProcessor(ProcessorBase):
    def process(self, url: str) -> ProcessingResult:
        """
        Process the content of a single webpage URL, converting it to chunks with metadata.

        Handles webpage conversion, chunk collection, preparation, and language detection.
        Includes a short delay to avoid rapid requests.

        Args:
            url (str): The URL of the webpage to process.

        Returns:
            ProcessingResult: The result containing chunks, source URL, and detected language.
            Returns None if conversion fails.
        """
        time.sleep(2)

        weblogger.info(f"Initiating processing pipeline for url {url}")
        self._logging_callback(f'Converting url {url}...', 20)
        try:
            document = self._converter.convert(url).document
        except Exception as e:
            weblogger.error(f"Failed to load the contents of the url page {url}: {e}")
            return ProcessingResult(source=url, chunks=None, lang='')
        
        self._logging_callback(f'Collecting chunks from {url}...', 40)
        collected_chunks = self._collect_chunks(document)
        document_content = MarkdownDocSerializer(doc=document).serialize().text

        self._logging_callback(f'Preparing chunks for {url} for importing...', 60)
        prepared_chunks = self._prepare_chunks(url, document_content, collected_chunks)

        weblogger.info(f"Successfully collected {len(collected_chunks)} chunks from {url}")
        
        return ProcessingResult(
            source=url,
            chunks=prepared_chunks,
            lang=detect_language(document_content), 
        )
