import json
from typing import Any
from cachetools import TTLCache

from .utils import get_cache_key
from src.cache.cache_base import CacheStrategy
from src.database.redisservice import RedisService
from src.utils.logging import get_logger
from src.config import config

logger = get_logger('cache_strat')

class RedisCache(CacheStrategy):
    def __init__(self, host, port, password, mode, metrics):
        service = RedisService(host, port, password, mode)
        self.client = service.get_client()
        self.metrics = metrics


    def set(self, key: str, value: Any, language: str, session_id: str):
        if not self.client: return
        
        try:
            json_str = json.dumps(value)
            cache_key = get_cache_key(key, language, session_id)
            self.client.set(cache_key, json_str, ex=config.cache.TTL_CACHE)
            logger.info(f"Cached response with key {cache_key[:20]}... to Redis")
        except Exception as e:
            logger.error(f"Could not write to Redis: {e}")


    def get(self, key: str, language: str, session_id: str):
        if not self.client: return None

        try:
            cache_key = get_cache_key(key, language, session_id)
            val = self.client.get(cache_key)
            if val is not None:
                self.metrics.increment_hit()
                logger.info(f"Found cached data with key {cache_key}")
                logger.debug(f"Cache statistics: Hit cache {self.metrics.cache_stats.hits} times, ratio[{self.metrics.cache_stats.hits_ratio}]")
                return json.loads(val)
            
            self.metrics.increment_miss()
            logger.debug(f"Cache statistics: Missed cache {self.metrics.cache_stats.misses} times, ratio[{self.metrics.cache_stats.hits_ratio}]")
            return None
        except Exception as e:
            logger.error(f"Could not read from Redis: {e}")
            return None
 

    def clear_cache(self):
        if not self.client: return

        try:
            self.client.flushdb()
            logger.info(f"Redis Cache cleared.")
        except Exception as e:
            logger.error(f"Could not clear Redis cache: {e}")
           

class LocalCache(CacheStrategy):
    def __init__(self, metrics):
        self.cache = TTLCache(maxsize=config.cache.MAX_SIZE_CACHE, ttl=config.cache.TTL_CACHE)
        self.metrics = metrics


    def set(self, key: str, value: Any, language: str, session_id: str):
        normalized_key = get_cache_key(key, language, session_id)
        self.cache[normalized_key] = value
        logger.info("Response cached")
 

    def get(self, key: str, language: str, session_id: str):
        normalized_key = get_cache_key(key, language, session_id)
        res = self.cache.get(normalized_key, None)
        if res is not None:
            self.metrics.increment_hit()
            logger.debug(f"Cache statistics: Hit cache {self.metrics.cache_stats.hits} times, ratio[{self.metrics.cache_stats.hits_ratio}]")
        else:
            self.metrics.increment_miss()
            logger.debug(f"Cache statistics: Missed cache {self.metrics.cache_stats.misses} times, ratio[{self.metrics.cache_stats.hits_ratio}]")
        return res


    def clear_cache(self):
        self.cache.clear()
        logger.info("Local Cache cleared.")
