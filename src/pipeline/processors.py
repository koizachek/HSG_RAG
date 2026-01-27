import os, re, json, importlib
import importlib.util 

from unstructured.partition.pdf  import partition_pdf
from unstructured.partition.text import partition_text
from unstructured.partition.json import partition_json
from unstructured.chunking.title import chunk_by_title

from src.pipeline.utilclasses import ProcessingResult
from config import CHUNK_SIZE, WeaviateConfiguration as wvtconf


# ------------ CLEANING FUNCTIONS -------------
def clean_spaced_text(text):
    """Cleans the OCR artifacts like sequences of single characters separated by spaces."""
    pattern = r'\b\w(\s+\w\b)+'
    text = re.sub(pattern, lambda m: ''.join(m.group(0).split()), text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def insert_spaces(text):
    """Inserts spaces for sequences of numebers and letters."""
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
    return text


class ProcessorBase:
    def __init__(self) -> None:
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

    def _prepare_chunks(self, document_name: str, document_content: str, chunks: list[str]) -> list[dict]:
        prepared_chunks = []
        for chunk in chunks:
            prepared_chunk = {}
            for prop, strat in self._strategies.items():
                prepared_chunk[prop] = strat.run(document_name, document_content, chunk)
            prepared_chunks.append(prepared_chunk)

        return prepared_chunks
    
    def _partitioning(self, path: str) -> list:
        raise NotImplementedError("This method must be implemented by child classes.")

    def _cleaning(self, elements: list) -> list:
        cleaning_tools = [
            clean_spaced_text,
            insert_spaces,
        ]

        for element in elements:
            for tool in cleaning_tools:
                element.text = tool(element.text)
    
    def _chunking(self, elements: list) -> list:
        return chunk_by_title(
            elements,
            max_characters=CHUNK_SIZE,
            new_after_n_chars=CHUNK_SIZE-112,
            combine_text_under_n_chars=100,
        )

    def process(self, path: str) -> ProcessingResult:
        # Step 1: Partition the source
        elements = self._partitioning(path)
        
        # Step 2: Fix broken fragments
        #self._cleaning(elements)

        # Step 3: Chunk the document contents
        chunks = self._chunking(elements)

        for chunk in chunks:
            print(chunk.text, end='\n\n')


class DocumentProcessor(ProcessorBase):
    def _partitioning(self, path: str) -> ProcessingResult:
        # Step 1: Partitioning strategy for different file types
        elements = []
        with open(path, 'rb') as f:
            if path.endswith('.pdf'):
                elements = partition_pdf(
                    file=f,
                    strategy='hi_res',
                    languages=['eng', 'deu'], 
                    skip_infer_table_types=False,
                    include_page_breaks=False
                )
            if path.endswith('.txt'):
                elements = partition_text(file=f)
            if path.endswith('.json'):
                elements = partition_json(file=f)

        return elements


class WebsiteProcessor(ProcessorBase):
    pass

