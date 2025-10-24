"""
Configuration settings for the Executive Education RAG Chatbot.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class LLMProviderConfiguration:
    AVAIABLE_PROVIDERS = ['ollama', 'groq', 'openai']
    LLM_PROVIDER = "ollama"

    # Groq settings
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = "mixtral-8x7b-32768"

    # OpenAI settings (keep as fallback)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = "gpt-3.5-turbo"

    # Local/Ollama settings
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODEL = "llama3.2"

    @classmethod
    def get_default_model(cls, provider: str = None) -> str:
        provider = provider or cls.LLM_PROVIDER
        return {
            "groq": cls.GROQ_MODEL,
            "openai": cls.OPENAI_MODEL, 
            "ollama": cls.OLLAMA_MODEL
        }.get(provider, cls.GROQ_MODEL)
    
    @classmethod
    def get_api_key(cls, provider: str = None) -> str:
        provider = provider or cls.LLM_PROVIDER
        return {
            "groq": cls.GROQ_API_KEY,
            "openai": cls.OPENAI_API_KEY
        }.get(provider)


# Scraper settings
SCRAPER_TIMEOUT = 30  # seconds
SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Data paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
PROCESSED_DATA_PATH = os.path.join(DATA_DIR, "processed_data.json")
VECTORDB_PATH = os.path.join(DATA_DIR, "vectordb")

# Vector database settings
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

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

