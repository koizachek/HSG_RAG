from docling.document_converter import InputFormat
from docling_core.types.doc.document import DoclingDocument, TitleItem

from ..pipeline.processors import ProcessorBase
from ..utils.logging import get_logger

logger = get_logger('scraper.processor')

class HTMLProcessor(ProcessorBase):
    def __init__(self) -> None:
        super().__init__()

    def process(self, url: str, html_content: str) -> DoclingDocument | None:
        if not html_content:
            logger.warning('Nothing to process, HTML body is empty!')
            return None

        logger.info(f"Analyzing page layout of URL '{url}'...")
        try:
            document = self._converter.convert_string(html_content, InputFormat.HTML).document
            document.name = url
            return document 
        except Exception as e:
            logger.error(f"Failed to analyze page layout: {e}")
            return None


    def extract_title(self, document: DoclingDocument) -> str:
        titles = [title.text for title in document.texts if isinstance(title, TitleItem)]
        return titles[0] if titles else 'No Title'


    def chunk(self, document: DoclingDocument) -> list[dict]:
        raw_chunks = list(self._chunker.chunk(document))
        chunks = self._merge_chunks_by_headings(raw_chunks) 

        prepared_chunks = [{
            'text': chunk,
            'title': chunk.split('\n')[0],
            'size': self._chunker.tokenizer.count_tokens(chunk)
        } for chunk in chunks]

        return prepared_chunks
    

    def _get_formatted_chunk_text(self, chunk, headings) -> str: 
            formatted_text = f"{' '.join(headings)}\n"

            if not hasattr(chunk.meta, 'doc_items'):
                return formatted_text + chunk.text.replace('\n', ' ')

            labels = set()       
            for item in chunk.meta.doc_items:
                labels.add(item.label)
            
            labels = [label for label in labels if label in ['table', 'list_item']]
            if labels:
                return formatted_text + chunk.text

            return formatted_text + chunk.text.replace('\n', ' ')


    def _merge_chunks_by_headings(self, raw_chunks: list) -> list[str]:
        """
        Groups consecutive chunks that share the same parent headings and merges them into one clean chunk.
        """
        prefix_level = 2
        merged = []
        i = 0
        n = len(raw_chunks)
        
        while i < n:
            chunk = raw_chunks[i]
            headings = getattr(chunk.meta, "headings", []) or []

            if len(headings) < prefix_level:
                formatted_text = self._get_formatted_chunk_text(chunk, headings) 
                merged.append(formatted_text)
                i += 1
                continue
            
            # Start a new group with this prefix
            common_prefix = "\n".join(headings[:prefix_level])
            group = []
            
            while i < n:
                curr_chunk = raw_chunks[i]
                curr_headings = getattr(curr_chunk.meta, "headings", []) or []
                curr_prefix = "\n".join(curr_headings[:prefix_level])
                
                if curr_prefix != common_prefix:
                    break 
                
                leaf_heading = curr_headings[-1] if len(curr_headings) > prefix_level else ""
                content = curr_chunk.text.replace('\n', ' ').strip()
                
                if leaf_heading and content:
                    group.append(f"{leaf_heading}: {content}")
                elif content:
                    group.append(content)
                
                i += 1
            
            # Build the final merged chunk
            if len(group) > 1:
                full_chunk = f"{'\n'.join(headings[1:-1])}\n{'\n'.join(group)}"
            else:
                full_chunk = f"{'\n'.join(headings[1:])}\n{chunk.text.replace('\n', ' ')}"

            merged.append(full_chunk.strip())
                
        return merged

