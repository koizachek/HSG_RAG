from src.config.configs import *
from functools import lru_cache
from typing import Any
import config as c

class AppConfig:
    # ===================== INITIALIZE YOUR SUBCONFIGS HERE =====================
    
    convstate:  ConversationStateConfig = ConversationStateConfig()
    processing: ProcessingConfig        = ProcessingConfig()
    weaviate:   WeaviateConfig          = WeaviateConfig()
    chain:      ChainConfig             = ChainConfig()
    cache:      CacheConfig             = CacheConfig()
    llm:        LLMProviderConfig       = LLMProviderConfig()
    
    # ===========================================================================

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves an extra parameter from config.py by name.
        
        Raises: 
            AttributeError if not found and no default provided.
        """
        try:
            return getattr(c, key)
        except AttributeError:
            if default is not None:
                return default
            raise AttributeError(f"Config parameter '{key}' is not defined!")

@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig()

config = get_config()
