from collections import defaultdict
import os, re

from pathlib import Path
from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer, ChunkingSerializerProvider
from docling_core.transforms.serializer.base import BaseTableSerializer, SerializationResult
from docling_core.transforms.serializer.common import create_ser_result
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
from docling_core.types.doc.document import DoclingDocument, RichTableCell, TableItem

from src.pipeline.utils import StrategiesProcessor, StrategyArguments
from src.pipeline.utilclasses import ProcessingResult, _logging_callback_placeholder
from src.utils.lang import detect_language
from src.utils.logging import get_logger
from src.config import config

weblogger  = get_logger("website_processor")
datalogger = get_logger("data_processor")

class EnchansedTableSerializer(BaseTableSerializer):
    def serialize(self, *, item, doc_serializer, doc, **kwargs) -> SerializationResult:
        if item.self_ref in doc_serializer.get_excluded_refs(**kwargs):
            return create_ser_result(text='')

        grid = item.data.grid
        if not grid: 
            return create_ser_result(text='')

        row_count = len(grid)
        col_count = len(grid[0]) if grid else 0

        if row_count < 7 or col_count < 3: 
            return create_ser_result(text='')
 
        row_cells = []
        for row in grid:
            clean_row = []
            for cell in row:
                if isinstance(cell, RichTableCell):
                    ser = doc_serializer.serialize(item=cell.ref.resolve(doc), **kwargs)
                    clean_row.append(ser.text.strip())
                else:
                    clean_row.append((cell.text or "").strip())
            if any(c for c in clean_row): 
                row_cells.append(clean_row)

        headers = row_cells[0]
        data_rows = row_cells[1:]

        lines = []

        for row in data_rows:
            if len(row) < 2 or not row[0].strip():
                continue

            main_key = row[0].strip().replace('\n', ' ')
            top_line = f'- {main_key}:'
            lines.append(top_line)

            for i in range(1, len(row)):
                value = row[i].strip().replace('\n', ' ')
                if not value: continue
                sub_header = headers[i].strip().replace('\n', ' ') if i < len(headers) else f""
                sub_line = f'  - {sub_header}: {value}'
                lines.append(sub_line)

            lines.append("")

        final_text = "\n".join(lines).rstrip() 
        return create_ser_result(text=final_text, span_source=item)


class EnchansedSerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=EnchansedTableSerializer(),
        )

class ProcessorBase:
    def __init__(self) -> None:
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
        tokenizer = AutoTokenizer.from_pretrained(config.processing.EMBEDDING_MODEL)
        self._chunker = HybridChunker(
            tokenizer=HuggingFaceTokenizer(
                tokenizer=tokenizer,
                max_tokens=config.processing.MAX_TOKENS
            ),
            serializer_provider=EnchansedSerializerProvider(),
            max_tokens=config.processing.MAX_TOKENS, 
            merge_peers=True
        )
        self.strategies_processor = StrategiesProcessor()
        self._logging_callback = config.dbapp['logging_callback'] or _logging_callback_placeholder
    

    def process(self):
        """
        Abstract method to be implemented by subclasses for processing sources.

        Raises:
            NotImplementedError: If not overridden in a subclass.
        """
        raise NotImplementedError("This method is not implemented in ProcessorBase")


    def convert_to_txt(self, document: DoclingDocument) -> str:
        plain_text = []
        for node, _ in document.iterate_items(root=document.body, with_groups=False):
            if isinstance(node, TableItem):
                df = node.export_to_dataframe(document)
                table_str = df.to_string(index=False, na_rep='')  
                plain_text.append(table_str)  
            elif hasattr(node, 'text') and node.text:
                plain_text.append(node.text.strip())
        return '\n\n'.join(plain_text)  


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
            prepared_chunk.append({
                prop: self.strategies_processor.apply_strategy(
                    strategy_name=prop,
                    arguments=StrategyArguments(document_name, document_content, chunk),
                )
                for prop in self.strategies_processor.list_strategies()
            })

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


class HTMLProcessor(ProcessorBase):
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
        if not url:
            return ProcessingResult(source=url, chunks=None, lang='')

        weblogger.info(f"Initiating processing pipeline for url {url}")
        self._logging_callback(f'Converting url {url}...', 20)
        try:
            document = self._converter.convert_string(url, InputFormat.HTML).document
        except Exception as e:
            weblogger.error(f"Failed to load the contents of the url page: {e}")
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
