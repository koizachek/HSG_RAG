from typing import Literal
from dotenv import load_dotenv 

import config, os

load_dotenv()

def _get(param: str, default=None, type_=None):
    value = getattr(config, param, default) 

    if value is None:
        value = os.getenv(param)

    if value is None:
        return default
    
    if not type_: return value
    
    try:
        return type_(value)
    except (ValueError, TypeError):
        raise ValueError(f"Failed to cast '{param}' value '{value}' to {type_.__name__}")


def _get_bool(param: str, default: bool = False) -> bool:
    value = _get(param, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


class ConfigBase:
    PARAMS: dict = dict()

    @classmethod
    def __getitem__(cls, key):
        return cls.PARAMS.get(key, None)

    @classmethod
    def __setitem__(cls, key, value):
        cls.PARAMS[key] = value


class DatabaseAppConfig(ConfigBase):
    pass


class PathsConfig(ConfigBase):
    DATA: str = _get('DATA_PATH')
    LOGS: str = _get('LOGS_PATH')
    URLS_OUTPUT:     str = os.path.join(_get('DATA_PATH'), 'urls')
    CHUNKS_OUTPUT:   str = os.path.join(_get('DATA_PATH'), 'chunks')
    TEMP_CHUNKS_OUTPUT: str = os.path.join(_get('DATA_PATH'), 'temp_chunks')
    SCRAPING_OUTPUT: str = os.path.join(_get('DATA_PATH'), 'scraping')
    RAW_TEXT_OUTPUT: str = os.path.join(_get('DATA_PATH'), 'raw_text')
    RAW_HTML_OUTPUT: str = os.path.join(_get('DATA_PATH'), 'raw_html')
    METADATA_OUTPUT: str = os.path.join(_get('DATA_PATH'), 'metadata')
    EXTRACTED_TEXT_OUTPUT: str = os.path.join(_get('DATA_PATH'), 'extracted_text')


class ScrapingConfig(ConfigBase):
    TIMEOUT: int      = _get('SCRAPING_TIMEOUT', 30)
    MAX_RETRIES: int  = _get('SCRAPING_MAX_RETRIES', 3)
    CRAWL_DELAY: int  = _get('SCRAPING_CRAWL_DELAY', 1)
    BACKOFF_RATE: int = _get('SCRAPING_BACKOFF_RATE', 2)
    TARGET_URLS: int  = _get('SCRAPING_TARGET_URLS', None)
    INTERVALS: dict = _get('SCRAPING_PRIO_INTERVAL', dict())


class ConversationStateConfig(ConfigBase):
    TRACK_USER_PROFILE = _get('TRACK_USER_PROFILE')
    LOCK_LANGUAGE_AFTER_N_MESSAGES = _get('LOCK_LANGUAGE_AFTER_N_MESSAGES')
    MAX_CONVERSATION_TURNS = _get('MAX_CONVERSATION_TURNS')


class ProcessingConfig(ConfigBase):
    LANG_AMBIGUITY_THRESHOLD: float = _get('LANG_AMBIGUITY_THRESHOLD')
    EMBEDDING_MODEL:          str   = _get('EMBEDDING_MODEL', 'openai/text-embedding-3-small')
    EMBEDDING_BASE_URL:       str   = _get('EMBEDDING_BASE_URL', 'https://openrouter.ai/api/v1')
    EMBEDDING_API_KEY:        str   = _get('EMBEDDING_API_KEY') or _get('OPEN_ROUTER_API_KEY')
    EMBEDDING_DIMENSIONS:     int   = _get('EMBEDDING_DIMENSIONS', 1536, type_=int)
    EMBEDDING_BATCH_SIZE:     int   = _get('EMBEDDING_BATCH_SIZE', 32, type_=int)
    EMBEDDING_VECTOR_NAME:    str   = _get('EMBEDDING_VECTOR_NAME', 'hsg_rag_embeddings')
    MAX_TOKENS:    int = _get('MAX_TOKENS')
    CHUNK_OVERLAP: int = _get('CHUNK_OVERLAP')


class ChainConfig(ConfigBase):
    ENABLE_RESPONSE_CHUNKING:  bool  = _get('ENABLE_RESPONSE_CHUNKING', False)
    # Latency fix: quality eval was a blocking LLM call AFTER each finished
    # answer (and discarded it on low score). Moved out of the request path;
    # re-enable only as async/offline evaluation.
    EVALUATE_RESPONSE_QUALITY: bool  = _get('ENABLE_EVALUATE_RESPONSE_QUALITY', False)
    CONFIDENCE_THRESHOLD:      float = _get('CONFIDENCE_THRESHOLD')

    # Hallucination fix: 4 chunks x 200 tokens (~800 tokens) was too little
    # grounding context, causing the model to fill gaps from world knowledge.
    TOP_K_RETRIEVAL: int = _get('TOP_K_RETRIEVAL', 8)
    MAX_RETRIES:     int = _get('MODEL_MAX_RETRIES', 2)
    # Latency fix: cap the conversation history sent to the agent per turn
    # (full history grew unbounded and made every turn slower and costlier).
    MAX_HISTORY_MESSAGES: int = _get('MAX_HISTORY_MESSAGES', 16)
    MAX_RESPONSE_WORDS_LEAD:     int = _get('MAX_RESPONSE_WORDS_LEAD', 350)
    MAX_RESPONSE_WORDS_SUBAGENT: int = _get('MAX_RESPONSE_WORDS_SUBAGENT', 200)


class CacheConfig(ConfigBase):
    ENABLED: bool = _get('CACHE_ENABLED', False)
    CACHE_MODE: Literal['local', 'cloud', 'dict'] = _get('CACHE_MODE')

    LOCAL_HOST: str = _get('CACHE_LOCAL_HOST', 'localhost')
    LOCAL_PORT: int = _get('CACHE_LOCAL_PORT', 6379)
    LOCAL_PASS: str = _get('CACHE_LOCAL_PASSWORD', '')
    
    CLOUD_HOST: str = _get('REDIS_CLOUD_HOST')
    CLOUD_PORT: int = _get('REDIS_CLOUD_PORT', type_=int)
    CLOUD_PASS: str = _get('REDIS_CLOUD_PASSWORD')

    TTL_CACHE:      int = _get('CACHE_TTL', 86400)
    MAX_SIZE_CACHE: int = _get('CACHE_MAX_SIZE', 1000)


class WeaviateConfig(ConfigBase):
    WEAVIATE_COLLECTION_BASENAME: str = _get('WEAVIATE_COLLECTION_BASENAME')
    
    BACKUP_METHODS: list[str] = ['manual', 'filesystem', 's3']
    BACKUP_METHOD: Literal['manual', 'filesystem', 's3'] = _get('WEAVIATE_BACKUP_METHOD')

    BACKUP_PATH:     str = _get('BACKUPS_PATH')
    PROPERTIES_PATH: str = _get('PROPERTIES_PATH')
    STRATEGIES_PATH: str = _get('STRATEGIES_PATH')

    CLUSTER_URL:          str = _get('WEAVIATE_CLUSTER_URL')
    WEAVIATE_API_KEY:     str = _get('WEAVIATE_API_KEY')
   
    INIT_TIMEOUT:   int  = _get('WEAVIATE_INIT_TIMEOUT', 90) 
    QUERY_TIMEOUT:  int  = _get('WEAVIATE_QUERY_TIMEOUT', 60) 
    INSERT_TIMEOUT: int  = _get('WEAVIATE_INSERT_TIMEOUT', 600)
    KEEP_WARM_ENABLED: bool = _get_bool('WEAVIATE_KEEP_WARM_ENABLED', True)
    KEEP_WARM_INTERVAL: int = _get('WEAVIATE_KEEP_WARM_INTERVAL', 180, type_=int)
    CLIENT_IDLE_TIMEOUT: int = _get('WEAVIATE_CLIENT_IDLE_TIMEOUT', 25 * 60, type_=int)


#TODO: Clean this configuration (outdated)
class LLMProvider:
    def __init__(self, base: str, sub: str | None = None) -> None:
        self.base = base
        self.sub  = sub
        self.name = f"{base}:{sub}" if sub else base 
    

    def with_sub(self, sub: str | None = None) -> str:
        return LLMProvider(self.base, sub)


class LLMConfig(ConfigBase):
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
            'meituan',
            'alibaba',   # For tongyi models
            'nvidia',
        ],
    }
    
    LLM_PROVIDER: LLMProvider = LLMProvider(_get('LLM_PROVIDER', 'openai'))

    MAIN_AGENT_MODEL: tuple[str, str] = _get('MAIN_AGENT_MODEL', ('openai', 'gpt-4.1'))
    FALLBACK_MODELS: list[tuple[str, str]] = _get('FALLBACK_MODELS', [('openai', 'gpt-5-mini')])
    LANGUAGE_DETECTION_MODEL: tuple[str, str] = _get('LANGUAGE_DETECTION_MODEL', ('openai', 'gpt-4o-mini'))
    CONFIDENCE_SCORING_MODEL: tuple[str, str] = _get('CONFIDENCE_SCORING_MODEL', ('openai', 'gpt-4o-mini'))
    SUMMARIZATION_MODEL: tuple[str, str] = _get('SUMMARIZATION_MODEL', ('openai', 'gpt-4.1'))
    
    # -------------------- Some predefined models for available providers ----------------------

    # Groq settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
    GROQ_MODEL:   str = "mixtral-8x7b-32768"
    
    # Open Router settings
    OPEN_ROUTER_API_KEY:  str = os.getenv("OPEN_ROUTER_API_KEY")
    OPEN_ROUTER_MODEL:    str = "meituan/longcat-flash-chat:free"
    OPEN_ROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # OpenAI settings
    # Latency fix: gpt-5.1 (reasoning model) replaced with a fast non-reasoning
    # model. Reasoning added 10-30s per agent loop without quality benefit for
    # this narrow advisory use case.
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    HUGGING_FACE_API_KEY: str = os.getenv("HUGGING_FACE_API_KEY")
    OPENAI_MODEL:   str = MAIN_AGENT_MODEL[1] if MAIN_AGENT_MODEL[0] == "openai" else _get('OPENAI_MODEL', 'gpt-4.1')
    
    # The gpt-oss:20b model is preferable but takes much more space
    # Set to False if you only have the llama3.2 installed
    GPT_OSS_ENABLED: bool = False
    # Local/Ollama settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL:    str = "gpt-oss:20b" if GPT_OSS_ENABLED else "llama3.2"
    
    # ----------------------------------------------------------------------------------------

    @classmethod
    def get_fallback_models(
        cls,
        provider: LLMProvider | None = None,
    ) -> list[tuple[LLMProvider, str]]:
        provider = provider or cls.LLM_PROVIDER
        match provider.base:
            case 'openai':
                # Latency fix: a single fallback model. A longer chain
                # multiplied worst-case latency (retries x fallbacks).
                return [
                    (LLMProvider(fallback_provider), fallback_model)
                    for fallback_provider, fallback_model in cls.FALLBACK_MODELS
                    if fallback_provider == 'openai'
                ]
            case 'open_router':
                return [
                    (provider.with_sub('openai'), "gpt-oss-20b"),
                    (provider.with_sub('openai'), "gpt-oss-120b"),
                    (provider.with_sub('alibaba'), "alibaba/tongyi-deepresearch-30b-a3b:free"),
                    (provider, "openrouter/polaris-alpha"),
                    # Currently unusable because has no tool support
                    #(provider.with_sub('deepseek'), "deepseek/deepseek-chat-v3.1:free"),
                ]
            case _:
                return []

    @classmethod
    def get_reasoning_support(cls, provider: LLMProvider | None = None) -> bool:
        provider = provider or cls.LLM_PROVIDER
        provider_base = provider.base if hasattr(provider, "base") else str(provider).split(":", 1)[0]
        return {
            "groq":   True,
            "openai": True, 
            "open_router": True,
        }.get(provider_base, False)


    @classmethod
    def get_default_model(cls, provider: LLMProvider | None = None) -> str:
        provider = provider or cls.LLM_PROVIDER
        provider_name = provider.name if hasattr(provider, "name") else str(provider)
        provider_base = provider.base if hasattr(provider, "base") else provider_name.split(":", 1)[0]
        if provider_name == cls.MAIN_AGENT_MODEL[0]:
            return cls.MAIN_AGENT_MODEL[1]
        return {
            "groq":   cls.GROQ_MODEL,
            "openai": cls.OPENAI_MODEL, 
            "ollama": cls.OLLAMA_MODEL,
            "open_router":   cls.OPEN_ROUTER_MODEL,
        }.get(provider_base)
   

    @classmethod
    def get_api_key(cls, provider: LLMProvider | None = None) -> str:
        provider = provider or cls.LLM_PROVIDER
        provider_name = provider.name if hasattr(provider, "name") else str(provider)
        provider_base = provider.base if hasattr(provider, "base") else provider_name.split(":", 1)[0]
        return {
            "groq": cls.GROQ_API_KEY,
            "openai": cls.OPENAI_API_KEY,
            "open_router": cls.OPEN_ROUTER_API_KEY,
        }.get(provider_base)


class NotificationCenterConfig(ConfigBase):
    ENABLE_EMAIL_ALERTS: bool = _get('NOTIFY_ENABLE_EMAIL_ALERTS', True, bool)

    SMTP_HOST: str = _get("NOTIFY_SMTP_HOST")
    SMTP_PORT: int = _get("NOTIFY_SMTP_PORT", 587, type_=int)

    SMTP_USER: str = _get("NOTIFY_SMTP_USER")
    SMTP_PASSWORD: str = _get("NOTIFY_SMTP_PASSWORD")

    SMTP_USE_TLS: bool = _get("NOTIFY_SMTP_USE_TLS", "True").lower() in ("1", "true", "yes", "on")

    FROM_EMAIL: str = _get("NOTIFY_FROM_EMAIL")
    TO_EMAIL: str = _get("NOTIFY_TO_EMAIL")

    ENABLE_SLACK_ALERTS: bool = _get('NOTIFY_ENABLE_SLACK_ALERTS', False, bool)
    SLACK_WEBHOOK_URL: str = _get("NOTIFY_SLACK_WEBHOOK_URL")
