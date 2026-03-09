import json, os

from typing import Counter
from docling_core.types.doc.document import DoclingDocument

from src.utils.logging  import get_logger
from src.scraping.utils import url_to_filename
from src.config import config

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
                node.hyperlink = None 
        
        logger.info(f"Extracted {len(discovered_urls)} URLs from source '{document.name}'")
        return discovered_urls


    def collect_repetitive_content(self, document: DoclingDocument) -> None:
        for node, _ in document.iterate_items(root=document.body, with_groups=False):
            if hasattr(node, 'text') and node.text:
                stripped_text = node.text.strip().lower()
                if len(stripped_text) < 50: 
                    self._repetitions_counter[stripped_text] += 1   
    

    def perform_content_analysis(self, target_url: str = "index") -> None:
        self._repetitive_content = [{'content': text, 'amount': count} 
            for text, count in self._repetitions_counter.items() if count > 1]
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


    def clean_furniture(self, document: DoclingDocument) -> None:
        document.furniture.children.clear()


    def clean_repetitive_content(self, document: DoclingDocument) -> None:
        for node, _ in document.iterate_items(root=document.body, with_groups=False):
            if hasattr(node, 'text') and node.text:
                stripped_text = node.text.strip().lower()
                if stripped_text in self._repetitive_content:
                    node.text = None

        # nodes_to_remove  = []
        # for node, _ in document.iterate_items(root=document.body, with_groups=False):
        #     if hasattr(node, 'text') and node.text:
        #         stripped_text = node.text.strip().lower()
        #         if stripped_text in self._repetitive_content:
        #             nodes_to_remove.append(node)
        #
        # for node in nodes_to_remove:
        #     if node.parent and hasattr(node.parent, 'children'):
        #         try:
        #             node.parent.children.remove(node)
        #         except ValueError:
        #             logger.error(f"Failed to remove node '{node.text if hasattr(node, 'text') else ''}': " +
        #                          f" node not found in parent children")
        #         except Exception as e:
        #             logger.error(f"Unexpected error removing node: {e}")
        #
        # logger.info(f"Removed {len(nodes_to_remove)} repetitive content elements " +
        #             f"from source '{document.name}'")
