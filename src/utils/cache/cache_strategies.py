from .cache_base import CacheStrategy
from cachetools import TTLCache
from config import TTL_CACHE as TTL, MAX_SIZE_CACHE as MAX_SIZE


class RedisCache(CacheStrategy):
    def __init__(self, redis_client):
        self.redis_client = redis_client

    def get(self, key):
        return self.redis_client.get(key)

    def set(self, key, value):
        self.redis_client.setex(key, TTL, value)

    def exists(self, key) -> bool:
        return self.redis_client.exists(key)
    
    def clear_cache(self):
        self.redis_client.flushdb()
    

class LocalCache(CacheStrategy):
    def __init__(self):
        self.cache = TTLCache(maxsize=MAX_SIZE, ttl=TTL)  # 1 day TTL

    def get(self, key):
        return self.cache.get(key, None)

    def set(self, key, value):
        self.cache[key] = value

    def exists(self, key) -> bool:
        return key in self.cache
