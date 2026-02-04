import os
from typing import Literal
from dotenv import load_dotenv 

import config 

load_dotenv()

def _get(param: str, default=None, type_=None):
    value = getattr(config, param, default) 

    if value is None:
        value = os.getenv(param)
    
    if not type_: return value
    
    try:
        return type_(value)
    except (ValueError, TypeError):
        raise ValueError(f"Failed to cast '{param}' value '{value}' to {type_.__name__}")

class ConversationStateConfig:
    TRACK_USER_PROFILE = _get('TRACK_USER_PROFILE')
    LOCK_LANGUAGE_AFTER_N_MESSAGES = _get('LOCK_LANGUAGE_AFTER_N_MESSAGES')
    MAX_CONVERSATION_TURNS = _get('MAX_CONVERSATION_TURNS')


class ProcessingConfig:
    LANG_AMBIGUITY_THRESHOLD: float = _get('LANG_AMBIGUITY_THRESHOLD')
    MAX_TOKENS:    int = _get('MAX_TOKENS')
    CHUNK_OVERLAP: int = _get('CHUNK_OVERLAP')


class ChainConfig:
    ENABLE_RESPONSE_CHUNKING:  bool  = _get('ENABLE_RESPONSE_CHUNKING', True)
    EVALUATE_RESPONSE_QUALITY: bool  = _get('ENABLE_EVALUATE_RESPONSE_QUALITY', True)
    CONFIDENCE_THRESHOLD:      float = _get('CONFIDENCE_THRESHOLD')
    
    TOP_K_RETRIEVAL: int = _get('TOP_K_RETRIEVAL', 4)
    MAX_RETRIES:     int = _get('MODEL_MAX_RETRIES', 3)
    MAX_RESPONSE_WORDS_LEAD:     int = _get('MAX_RESPONSE_WORDS_LEAD', 100)
    MAX_RESPONSE_WORDS_SUBAGENT: int = _get('MAX_RESPONSE_WORDS_SUBAGENT', 200)


class CacheConfig:
    CACHE_MODE: Literal['local', 'cloud', 'dict'] = _get('CACHE_MODE')

    LOCAL_HOST: str = _get('CACHE_LOCAL_HOST', 'localhost')
    LOCAL_PORT: int = _get('CACHE_LOCAL_PORT', 6379)
    LOCAL_PASS: str = _get('CACHE_LOCAL_PASSWORD', '')
    
    CLOUD_HOST: str = _get('REDIS_CLOUD_HOST')
    CLOUD_PORT: int = _get('REDIS_CLOUD_PORT', type_=int)
    CLOUD_PASS: str = _get('REDIS_CLOUD_PASSWORD')

    TTL_CACHE:      int = _get('CACHE_TTL', 86400)
    MAX_SIZE_CACHE: int = _get('CACHE_MAX_SIZE', 1000)


class WeaviateConfig:
    LOCAL_DATABASE: bool = _get('WEAVIATE_IS_LOCAL')
    WEAVIATE_COLLECTION_BASENAME: str = _get('WEAVIATE_COLLECTION_BASENAME')
    
    BACKUP_METHODS: list[str] = ['manual', 'filesystem', 's3']
    BACKUP_METHOD: Literal['manual', 'filesystem', 's3'] = _get('WEAVIATE_BACKUP_METHOD')

    BACKUP_PATH:     str = _get('BACKUPS_PATH')
    PROPERTIES_PATH: str = _get('PROPERTIES_PATH')
    STRATEGIES_PATH: str = _get('STRATEGIES_PATH')

    CLUSTER_URL:          str = _get('WEAVIATE_CLUSTER_URL')
    WEAVIATE_API_KEY:     str = _get('WEAVIATE_API_KEY')
    HUGGING_FACE_API_KEY: str = _get('HUGGING_FACE_API_KEY')
   
    INIT_TIMEOUT:   int  = _get('WEAVIATE_INIT_TIMEOUT', 90) 
    QUERY_TIMEOUT:  int  = _get('WEAVIATE_QUERY_TIMEOUT', 60) 
    INSERT_TIMEOUT: int  = _get('WEAVIATE_INSERT_TIMEOUT', 600)


#TODO: Clean this configuration (outdated)
class LLMProvider:
    def __init__(self, base: str, sub: str | None = None) -> None:
        self.base = base
        self.sub  = sub
        self.name = f"{base}:{sub}" if sub else base 
    

    def with_sub(self, sub: str | None = None) -> str:
        return LLMProvider(self.base, sub)


class LLMProviderConfig:
    AVAIABLE_PROVIDERS: list[str] = [
        'groq', 
        'ollama',  
        'openai',
        'open_router',
    ]
    AVAILABLE_SUBPROVIDERS: dict = {
        'groq': [],
        'open_router': [
            'openai', 
            'deepseek',
            'meituan'
            'alibaba'   # For tongyi models 
            'nvidia',
        ],
    }
    
    LLM_PROVIDER: LLMProvider = LLMProvider('openai')
    
    # -------------------- Some predefined models for available providers ----------------------

    # Groq settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
    GROQ_MODEL:   str = "mixtral-8x7b-32768"
    
    # Open Router settings
    OPEN_ROUTER_API_KEY:  str = os.getenv("OPEN_ROUTER_API_KEY")
    OPEN_ROUTER_MODEL:    str = "meituan/longcat-flash-chat:free"
    OPEN_ROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # OpenAI settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL:   str = "gpt-5.1"
    
    # The gpt-oss:20b model is preferable but takes much more space
    # Set to False if you only have the llama3.2 installed
    GPT_OSS_ENABLED: bool = False
    # Local/Ollama settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL:    str = "gpt-oss:20b" if GPT_OSS_ENABLED else "llama3.2"
    
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
