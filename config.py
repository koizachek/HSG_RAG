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
    LLM_PROVIDER = LLMProvider('openai')
    
    # -------------------- Some predefined models for available providers ----------------------

    # Groq settings
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GROQ_MODEL = "mixtral-8x7b-32768"
    
    # Open Router settings
    OPEN_ROUTER_API_KEY = os.getenv("OPEN_ROUTER_API_KEY")
    OPEN_ROUTER_MODEL="meituan/longcat-flash-chat:free"
    OPEN_ROUTER_BASE_URL="https://openrouter.ai/api/v1"

    # OpenAI settings
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL = "gpt-5.1"
    
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
                    provider.with_sub('openai'):   "gpt-oss-20b",
                    provider.with_sub('openai'):   "gpt-oss-120b",
                    provider.with_sub('alibaba'):  "alibaba/tongyi-deepresearch-30b-a3b:free",
                    provider: "openrouter/polaris-alpha",
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


# Weaviate database settings 
class WeaviateConfiguration:
    LOCAL_DATABASE = False
    WEAVIATE_COLLECTION_BASENAME = 'hsg_rag_content'
    
    # Weaviate backup settings
    AVAILABLE_BACKUP_METHODS = ['manual', 'filesystem', 's3']
    BACKUP_METHOD = 'manual'

    # Weaviate generated data paths
    BACKUP_PATH = 'data/database/backups'
    PROPERTIES_PATH = 'data/database/properties'
    STRATEGIES_PATH = 'data/database/strategies'

    # Weaviate Cloud settings
    CLUSTER_URL = os.getenv('WEAVIATE_CLUSTER_URL')
    WEAVIATE_API_KEY = os.getenv('WEAVIATE_API_KEY')
    HUGGING_FACE_API_KEY = os.getenv('HUGGING_FACE_API_KEY')
    
    # Custom timeouts for Cloud connection (in seconds)
    INIT_TIMEOUT   = 90 
    QUERY_TIMEOUT  = 60 
    INSERT_TIMEOUT = 600

    @classmethod 
    def is_local(cls) -> bool:
        return cls.LOCAL_DATABASE

# Cache settings
class CacheConfig:
    LOCAL_HOST = "localhost"
    LOCAL_PORT = 6379
    LOCAL_PASS = os.getenv("REDIS_LOCAL_PASSWORD", "")

    CLOUD_HOST = os.getenv("REDIS_CLOUD_HOST")
    CLOUD_PORT = int(os.getenv("REDIS_CLOUD_PORT", 6379))
    CLOUD_PASS = os.getenv("REDIS_CLOUD_PASSWORD")

    CACHE_LOCAL = "local"
    CACHE_CLOUD = "cloud"
    CACHE_DICT = "dict"
    CACHE_MODE = "cloud"  # 'local' or 'cloud' or 'dict' set here the default cache mode

    TTL_CACHE = 86400 # 86400 seconds = 24 hours
    MAX_SIZE_CACHE = 1000

# Data paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
PROCESSED_DATA_PATH = os.path.join(DATA_DIR, "processed_data.json")
VECTORDB_PATH = os.path.join(DATA_DIR, "vectordb")

# Determines when the text is considered German during the language detection
LANG_AMBIGUITY_THRESHOLD = 0.6

# Confidence Threshold to activate fall-back mechanism
CONFIDENCE_THRESHOLD = 0.6

# Vector database settings
CHUNK_SIZE = 512
CHUNK_OVERLAP = 200

# Agent Chain settings 
MAX_MODEL_RETRIES = 3

# RAG settings
TOP_K_RETRIEVAL = 4  # Number of documents to retrieve for each query

# UI settings
MAX_HISTORY = 10  # Maximum number of conversation turns to keep in history

# Response formatting settings
MAX_RESPONSE_WORDS_LEAD = 100  # Maximum words for lead agent responses
MAX_RESPONSE_WORDS_SUBAGENT = 200  # Maximum words for subagent responses
ENABLE_RESPONSE_CHUNKING = True  # Break long responses into multiple turns

# Evaluation of agent response quality 
ENABLE_EVALUATE_RESPONSE_QUALITY = True

# Conversation state settings
TRACK_USER_PROFILE = True  # Track user preferences and avoid repetition
LOCK_LANGUAGE_AFTER_N_MESSAGES = 3  # Lock language after N user messages (0 = never lock)
MAX_CONVERSATION_TURNS = 15 # End conversation after max turns reached

# Data processing pipeline settings 
CHUNK_MAX_TOKENS = 8191
AVAILABLE_LANGUAGES = ['en', 'de']
HASH_FILE_PATH = os.path.join(DATA_DIR, 'hashtables.json')
DOCUMENTS_PATH = os.path.join(DATA_DIR, 'documents')

# Base URL for scraping
BASE_URL = "https://emba.unisg.ch/programm"
