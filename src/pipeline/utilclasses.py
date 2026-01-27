from dataclasses import dataclass

def _logging_callback_placeholder(*_):
    pass

def _deduplication_callback_placeholder(*_) -> bool:
    return False

@dataclass
class ProcessingResult:
    chunks: list[dict]
    source: str 
    lang:   str


