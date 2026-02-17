from threading import Lock
from src.cache.cache_metrics import CacheMetrics
from src.cache.cache_strategies import RedisCache, LocalCache

from src.utils.logging import get_logger
from src.config import config

logger = get_logger("cache    ")

class Cache:
    _instance = None
    _settings = None
    _lock = Lock()
    _cache_metrics = None

    @staticmethod
    def configure(mode: str, no_cache: bool):
        Cache._settings = {
            "mode": mode,
            "enabled": not no_cache
        }

    @staticmethod
    def get_cache():
        if Cache._instance is not None:
            return Cache._instance

        with Cache._lock:
            if Cache._instance is not None:
                return Cache._instance

            settings = Cache._settings or {"mode": 'local', "enabled": True}
            
            if not settings.get("enabled", True):
                Cache._instance = None
                return None
            
            if Cache._cache_metrics is None:
                Cache._cache_metrics = CacheMetrics()

            mode = settings.get("mode", 'local')
            
            if mode == 'cloud':
                cache_obj = RedisCache(
                    host=config.cache.CLOUD_HOST,
                    port=config.cache.CLOUD_PORT,
                    password=config.cache.CLOUD_PASS,
                    mode=mode,
                    metrics=Cache._cache_metrics
                )
            elif mode == 'local':
                cache_obj = RedisCache(
                    host=config.cache.LOCAL_HOST,
                    port=config.cache.LOCAL_PORT,
                    password=config.cache.LOCAL_PASS,
                    mode=mode,
                    metrics=Cache._cache_metrics
                )
            elif mode == 'dict':
                Cache._instance = LocalCache(metrics=Cache._cache_metrics)
                return Cache._instance
            else:
                logger.error("FALLBACK to dict cache. Unknown cache mode")
                Cache._instance = LocalCache(metrics=Cache._cache_metrics)
                return Cache._instance
            
            if cache_obj.client is None:
                logger.error("FALLBACK to dict cache. Redis connection failed")
                Cache._instance = LocalCache(metrics=Cache._cache_metrics)
            else: 
                Cache._instance = cache_obj

            return Cache._instance
