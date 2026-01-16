from .cache_base import CacheStrategy
from cachetools import TTLCache
from config import TTL_CACHE as TTL, MAX_SIZE_CACHE as MAX_SIZE


class RedisCache(CacheStrategy):
    def __init__(self, redis_client):
        self._redis_client = redis_client

    def get(self, key):
        return self._redis_client.get(key)

    def set(self, key, value):
        self._redis_client.setex(key, TTL, value)
    
    def clear_cache(self):
        self._redis_client.flushdb()
    

class LocalCache(CacheStrategy):
    def __init__(self):
        self._cache = TTLCache(maxsize=MAX_SIZE, ttl=TTL)

    def set(self, key, value):
        self._cache[key] = value
    
    def get(self, key):
        return self._cache.get(key, None)

    def clear_cache(self):
        self._cache.clear()