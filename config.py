"""
Configuration settings for the Executive Education RAG Chatbot.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class LLMProvider:
    def __init__(self, base: str, sub: str | None = None) -> None:
        self.base = base
        self.sub  = sub
        self.name = f"{base}:{sub}" if sub else base 
    

    def with_sub(self, sub: str | None = None) -> str:
        return LLMProvider(self.base, sub)


class LLMProviderConfiguration:
    AVAIABLE_PROVIDERS = [
        'groq', 
        'ollama',  
        'openai',
        'open_router',
    ]
    AVAILABLE_SUBPROVIDERS = {
        'groq': [],
        'open_router': [
            'openai', 
            'deepseek',
            'meituan'
            'alibaba'   # For tongyi models 
            'nvidia',
        ],
    }
    
    # DEFINE YOUR MAIN MODEL PROVIDER HERE 
    # Some unified interfaces such as Groq or Open Router provide access to other providers
    # such as OpenAI or Deepseek. When using interfaces define the provider you want to gain access to. 
    LLM_PROVIDER = LLMProvider(base='open_router', sub='nvidia')
    
    # -------------------- Some predefined models for available providers ----------------------

    # Groq settings
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = "mixtral-8x7b-32768"
    
    # Open Router settings
    OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY")
    OPEN_ROUTER_MODEL="gpt-oss-20b:free"
    OPEN_ROUTER_BASE_URL="https://openrouter.ai/api/v1"

    # OpenAI settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = "gpt-5"
    
    # The gpt-oss:20b model is preferable but takes much more space
    # Set to False if you only have the llama3.2 installed
    GPT_OSS_ENABLED=False
    # Local/Ollama settings
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODEL = "gpt-oss:20b" if GPT_OSS_ENABLED else "llama3.2"
    
    # ----------------------------------------------------------------------------------------

    @classmethod
    def get_fallback_models(cls, provider: LLMProvider | None = None) -> list[str]:
        provider = provider or cls.LLM_PROVIDER
        match provider.base:
            case 'openai':
                return {
                    provider: fallback_model
                    for fallback_model in [
                        'gpt-5-mini', 
                        'gpt-5-nano',
                    ]
                }
            case 'open_router':
                return {
                    provider.with_sub('meituan'):  "meituan/longcat-flash-chat:free",
                    provider.with_sub('alibaba'):  "alibaba/tongyi-deepresearch-30b-a3b:free",
                    # Currently unusable because has no tool support
                    #provider.with_sub('deepseek'): "deepseek/deepseek-chat-v3.1:free",
                }
            case _:
                return {}

    @classmethod
    def get_reasoning_support(cls, provider: LLMProvider | None = None) -> bool:
        provider = provider or cls.LLM_PROVIDER
        return {
            "groq":   True,
            "openai": True, 
            "open_router": True,
        }.get(provider.base, False)


    @classmethod
    def get_default_model(cls, provider: LLMProvider | None = None) -> str:
        provider = provider or cls.LLM_PROVIDER
        return {
            "groq":   cls.GROQ_MODEL,
            "openai": cls.OPENAI_MODEL, 
            "ollama": cls.OLLAMA_MODEL,
            "open_router":   cls.OPEN_ROUTER_MODEL,
        }.get(provider.base)
   

    @classmethod
    def get_api_key(cls, provider: LLMProvider | None = None) -> str:
        provider = provider or cls.LLM_PROVIDER
        return {
            "groq": cls.GROQ_API_KEY,
            "openai": cls.OPENAI_API_KEY,
            "open_router": cls.OPEN_ROUTER_API_KEY,
        }.get(provider.base)


# Data paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
PROCESSED_DATA_PATH = os.path.join(DATA_DIR, "processed_data.json")
VECTORDB_PATH = os.path.join(DATA_DIR, "vectordb")

# Vector database settings
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Agent Chain settings 
MAX_MODEL_RETRIES = 1

# RAG settings
TOP_K_RETRIEVAL = 8  # Number of documents to retrieve for each query

# UI settings
MAX_HISTORY = 10  # Maximum number of conversation turns to keep in history

# Data processing pipeline settings 
CHUNK_MAX_TOKENS = 8191
AVAILABLE_LANGUAGES = ['en', 'de']
HASH_FILE_PATH = os.path.join(DATA_DIR, 'hashtables.json')
DOCUMENTS_PATH = os.path.join(DATA_DIR, 'documents')

# Base URL for scraping
BASE_URL = "https://emba.unisg.ch/programm"

# Weaviate database settings 
WEAVIATE_BACKUP_BACKEND = ''
WEAVIATE_COLLECTION_BASENAME = 'hsg_rag_content'

