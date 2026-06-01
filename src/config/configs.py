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


class LoggingConfig(ConfigBase):
    MAX_RUNS: int = _get('LOG_MAX_RUNS', 10, type_=int)
    CATEGORIES: dict[str, list[str]] = _get(
        'LOG_CATEGORIES',
        {
            "all": ["*"],
            "scraping": ["scraper", "pipeline", "weaviate"],
            "weaviate": ["weaviate"],
        },
    )


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
    EMBEDDING_MODEL:          float = _get('EMBEDDING_MODEL')
    MAX_TOKENS:    int = _get('MAX_TOKENS')
    CHUNK_OVERLAP: int = _get('CHUNK_OVERLAP')


class ChainConfig(ConfigBase):
    ENABLE_SUBAGENTS:          bool  = _get('ENABLE_SUBAGENTS', False)
    ENABLE_RESPONSE_CHUNKING:  bool  = _get('ENABLE_RESPONSE_CHUNKING', False)
    EVALUATE_RESPONSE_QUALITY: bool  = _get('ENABLE_EVALUATE_RESPONSE_QUALITY', True)
    CONFIDENCE_THRESHOLD:      float = _get('CONFIDENCE_THRESHOLD')
    
    TOP_K_RETRIEVAL: int = _get('TOP_K_RETRIEVAL', 4)
    MAX_RETRIES:     int = _get('MODEL_MAX_RETRIES', 3)
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
    KEEP_WARM_ENABLED: bool = _get_bool('WEAVIATE_KEEP_WARM_ENABLED', True)
    KEEP_WARM_INTERVAL: int = _get('WEAVIATE_KEEP_WARM_INTERVAL', 45, type_=int)
    CLIENT_IDLE_TIMEOUT: int = _get('WEAVIATE_CLIENT_IDLE_TIMEOUT', 25 * 60, type_=int)


class LLMConfig(ConfigBase):
    MAIN_AGENT_MODEL: tuple[str, str] = _get('MAIN_AGENT_MODEL')
    SUBAGENT_MODEL: tuple[str, str] = _get('SUBAGENT_MODEL')
    LANGUAGE_DETECTION_MODEL: tuple[str, str] = _get('LANGUAGE_DETECTION_MODEL')
    CONFIDENCE_SCORING_MODEL: tuple[str, str] = _get('CONFIDENCE_SCORING_MODEL')
    SUMMARIZATION_MODEL: tuple[str, str] = _get('SUMMARIZATION_MODEL')
    FALLBACK_MODELS: list[tuple[str, str]] = _get('FALLBACK_MODELS')
    
    GROQ_API_KEY:   str = _get('GROQ_API_KEY', default=None)
    OPENAI_API_KEY: str = _get('OPENAI_API_KEY', default=None)
    OPENROUTER_API_KEY:  str = _get('OPENROUTER_API_KEY', default=None)
    HUGGING_FACE_API_KEY: str = _get('HUGGING_FACE_API_KEY', default=None)

    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1" 
    OLLAMA_BASE_URL: str = "http://localhost:11434" 


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
