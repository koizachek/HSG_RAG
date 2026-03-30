from dataclasses import asdict, dataclass, is_dataclass 
from datetime import datetime

from docling_core.types.doc.document import DoclingDocument

@dataclass 
class FetchResult:
    final_url:     str
    last_modified: datetime
    etag:          str

    not_modified:  bool = False 
    text:          str  = ''
    page_hash:     str  = ''

@dataclass 
class PageData:
    url:           str 
    last_modified: datetime

@dataclass 
class UrlTags:
    topic:    str 
    priority: str 
    language: str 
    program:  str

@dataclass 
class UrlTimestamps:
    last_modified: datetime 
    last_scraped:  datetime 
    etag:          str 
    page_hash:     str

@dataclass 
class DocumentTags:
    program:  str 
    language: str 

@dataclass 
class TaggedDocument:
    document: DoclingDocument
    tags:     DocumentTags

@dataclass 
class ChunkMetadata:
    chunk_id:        str 
    text:            str 
    source_url:      str 
    program:         str 
    language:        str 
    topic:           str 
    last_scraped:    datetime 
    page_title:      str 
    section_heading: str 
    token_size:      int

@dataclass 
class ScrapingResult:
    document:        DoclingDocument
    discovered_urls: list[str]
    final_url:       str 
    timestamps:      UrlTimestamps
    discovery_depth: int 

@dataclass 
class DomainAnalysisReport:
    target: str 
    pages:  list[PageData]
    urls:   list[str]
    delay:  float

@dataclass 
class UrlAnalysisReport:
    documents:       list[DoclingDocument]
    discovered_urls: list[str]  

@dataclass 
class DocumentAnalysisReport:
    url_tags:         dict[str, UrlTags]
    url_priorities:   dict[str, list[str]]
    tagged_documents: list[TaggedDocument]


def dataclass_to_dict(obj) -> dict:
    if not is_dataclass(obj): return obj
    return asdict(obj, dict_factory=lambda items: {
        k: v.isoformat() if isinstance(v, datetime) else v
        for k, v in items
    })


def dict_to_url_timestamps(data: dict) -> UrlTimestamps:
    from .utils import parse_isoformat

    if not data: return None  
    
    data['last_modified'] = parse_isoformat(data.get('last_modified'))
    data['last_scraped']  = parse_isoformat(data.get('last_scraped'))
    
    return UrlTimestamps(**data)
