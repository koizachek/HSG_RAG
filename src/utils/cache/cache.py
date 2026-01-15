from .cache_strategies import RedisCache, LocalCache
from config import CASHE_STRATEGY

class Cache:
    
    @staticmethod
    def get_cache():
        if CASHE_STRATEGY == 'REDIS':
            return RedisCache()
        elif CASHE_STRATEGY == 'LOCAL':
            return LocalCache()
        else:
            raise ValueError("Invalid cache strategy")