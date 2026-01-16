from .cache_base import CacheStrategy
from cachetools import TTLCache
from config import TTL_CACHE as TTL, MAX_SIZE_CACHE as MAX_SIZE
import json
from src.database.redisservice import RedisService
from src.utils.logging import get_logger

logger = get_logger(__name__)

class RedisCache(CacheStrategy):
    def __init__(self):
        service = RedisService()
        self.client = service.get_client()

    def set(self, key: str, value: dict, ttl: int = 86400):
        if not self.client: return

        try:
            json_str = json.dumps(value)
            self.client.set(key, json_str, ex=ttl)
        except Exception as e:
            logger.error(f"Could not write to Redis: {e}")

    def get(self, key: str):
        if not self.client: return None

        try:
            val = self.client.get(key)
            if val:
                return json.loads(val)
            return None
        except Exception as e:
            logger.error(f"Could not read from Redis: {e}")
            return None
    
    def clear_cache(self):
        if not self.client: return

        try:
            self.client.flushdb()
            logger.info("Redis Cache cleared.")
        except Exception as e:
            logger.error(f"Could not clear Redis cache: {e}")
           

class LocalCache(CacheStrategy):
    def __init__(self):
        self._cache = TTLCache(maxsize=MAX_SIZE, ttl=TTL)

    def set(self, key, value):
        self._cache[key] = value
    
    def get(self, key):
        return self._cache.get(key, None)

    def clear_cache(self):
        self._cache.clear()