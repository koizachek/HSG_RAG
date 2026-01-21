from .cache_base import CacheStrategy
from config import CacheConfig
from cachetools import TTLCache
import json
from typing import Any
from src.database.redisservice import RedisService
from src.utils.logging import get_logger

logger = get_logger(__name__)

class RedisCache(CacheStrategy):
    def __init__(self, host, port, password, mode, metrics):
        service = RedisService(host, port, password, mode)
        self.client = service.get_client()
        self.metrics = metrics

    def set(self, key: str, value: Any, language: str):
        if not self.client: return
        
        try:
            json_str = json.dumps(value)
            self.client.set(self._generate_normalized_key(key, language), json_str, ex=CacheConfig.TTL_CACHE)
            logger.info("Response cached")
        except Exception as e:
            logger.error(f"Could not write to Redis: {e}")

    def get(self, key: str, language: str):
        if not self.client: return None

        try:
            val = self.client.get(self._generate_normalized_key(key, language))
            if val is not None:
                self.metrics.increment_hit()
                logger.info(f"Cache HIT {self.metrics.cache_stats.hits} {self.metrics.cache_stats.hits_ratio}")
                return json.loads(val)
            
            self.metrics.increment_miss()
            logger.info(f"Cache MISS {self.metrics.cache_stats.misses} {self.metrics.cache_stats.hits_ratio}")
            return None
        except Exception as e:
            logger.error(f"Could not read from Redis: {e}")
            return None

    def _generate_normalized_key(self, key: str, language: str) -> str:
        import re

        normalized_key = re.sub(r'[^a-z0-9]', '', key.lower())
        return f"cache:{language}:{normalized_key}"
    
    def clear_cache(self):
        if not self.client: return

        try:
            self.client.flushdb()
            logger.info(f"Redis Cache cleared.")
        except Exception as e:
            logger.error(f"Could not clear Redis cache: {e}")
           

class LocalCache(CacheStrategy):
    def __init__(self, metrics):
        self.cache = TTLCache(maxsize=CacheConfig.MAX_SIZE_CACHE, ttl=CacheConfig.TTL_CACHE)
        self.metrics = metrics

    def _generate_normalized_key(self, key: str, language: str) -> str:
        import re
        
        normalized_key = re.sub(r'[^a-z0-9]', '', key.lower())
        return f"cache:{language}:{normalized_key}"

    def set(self, key: str, value: Any, language: str):
        normalized_key = self._generate_normalized_key(key, language)
        self.cache[normalized_key] = value
        logger.info("Response cached")
    
    def get(self, key: str, language: str):
        normalized_key = self._generate_normalized_key(key, language)
        res = self.cache.get(normalized_key, None)
        if res is not None:
            self.metrics.increment_hit()
            logger.info(f"Cache HIT {self.metrics.cache_stats.hits} {self.metrics.cache_stats.hits_ratio}")
        else:
            self.metrics.increment_miss()
            logger.info(f"Cache MISS {self.metrics.cache_stats.misses}")
        return res

    def clear_cache(self):
        self.cache.clear()
        logger.info("Local Cache cleared.")