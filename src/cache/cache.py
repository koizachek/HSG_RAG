from .cache_strategies import RedisCache, LocalCache
from config import CACHE_STRATEGY, CACHE_ENABLED

class Cache:
    
    @staticmethod
    def get_cache():
        if not CACHE_ENABLED:
            return None
        if CACHE_STRATEGY == 'REDIS':
            return RedisCache()
        elif CACHE_STRATEGY == 'LOCAL':
            return LocalCache()
        else:
            raise ValueError("Invalid cache strategy")