import json, os

from typing import Counter
from docling_core.types.doc.document import DoclingDocument

from .utils import url_to_filename

from ..const.cc_whitelist import REPETITION_WHITELIST
from ..utils.logging import get_logger
from ..config import config

logger = get_logger('scraper.cleaning')

class ContentCleaner:
    def __init__(self) -> None:
        self._repetitions_counter: Counter = Counter()
        self._repetitive_content:  list[str] = []


    def extract_urls(self, document: DoclingDocument) -> list[str]:
        discovered_urls = []
        for node, _ in document.iterate_items(root=document.body, with_groups=False):
            if hasattr(node, 'hyperlink') and node.hyperlink:
                discovered_urls.append(str(node.hyperlink))
        
        return discovered_urls


    def collect_repetitive_content(self, document: DoclingDocument) -> None:
        content_in_document = set()
        for node, _ in document.iterate_items(root=document.body, with_groups=False):
            if hasattr(node, 'text') and node.text:
                stripped_text = node.text.strip().lower()
                content_in_document.add(stripped_text)
        
        for content in content_in_document:
            self._repetitions_counter[content] += 1   
    

    def perform_content_analysis(self, target_url: str = "index") -> None:
        self._repetitive_content = [{'content': text, 'amount': count} 
            for text, count in self._repetitions_counter.items() 
                if text not in REPETITION_WHITELIST and count > 1]
        logger.info(f"Content analysis for target URL '{target_url}' " + 
                    f"yielded {len(self._repetitive_content)} repetitive text lines")

        content_analysis = {
            'target_url': target_url,
            'repetitive_content': self._repetitive_content,
        }
        target_url_filename = url_to_filename(target_url) + '-content_analysis.json'
        target_url_path = os.path.join(config.paths.SCRAPING_OUTPUT, target_url_filename) 
        with open(target_url_path, 'w') as f:
            json.dump(content_analysis, f, indent=4)        
        logger.info(f"Saved content analysis results under '{target_url_path}'")

        self._repetitive_content = [rc['content'] for rc in self._repetitive_content]


    def clean_document(self, document: DoclingDocument) -> None:
        document.furniture.children.clear()
        
        # Step 1: Shallow tagging of useless content
        texts_to_remove = set()
        nodes_to_remove = []
        for node, _ in document.iterate_items(root=document.body, with_groups=False):            
            if hasattr(node, 'text') and node.text:
                stripped_text = node.text.strip().lower()
                if stripped_text in self._repetitive_content:
                    nodes_to_remove.append(node)
                    continue
            if hasattr(node, 'captions') and node.captions:
                caption_text = node.caption_text(document).strip()
                if len(caption_text) < 50:
                    nodes_to_remove.append(node)
                    if caption_text not in self._repetitive_content:
                        texts_to_remove.add(caption_text)
                    continue
            if hasattr(node, 'hyperlink') and node.hyperlink:
                nodes_to_remove.append(node)
                if node.text:
                    texts_to_remove.add(node.text)
                continue
        
        # Step 2: Removal of duplicates from other node types
        for node, _ in document.iterate_items(root=document.body, with_groups=False):
            if hasattr(node, 'text') and node.text:
                stripped_text = node.text.strip().lower()
                if stripped_text in texts_to_remove:
                    nodes_to_remove.append(node)
                    continue

        # Step 3: Deletion of all useless nodes
        for node in nodes_to_remove:
            if not (hasattr(node, 'parent') and node.parent): 
                continue
            
            parent_node = node.parent.resolve(document)
            node_ref = node.get_ref()
            if node_ref not in parent_node.children:
                continue
            
            node_children_refs = list(node.children) if hasattr(node, 'children') else []
            idx = parent_node.children.index(node_ref)
            parent_node.children.pop(idx)
            parent_node.children[idx:idx] = node_children_refs
            
            # Promote children of removed node to node's parent
            for child_ref in node_children_refs:
                child_node = child_ref.resolve(document)
                if hasattr(child_node, 'parent'):
                    child_node.parent = node.parent 
            
            # Clean node references
            if hasattr(node, 'children'):
                node.children.clear()
            if hasattr(node, 'parent'):
                node.parent = None

