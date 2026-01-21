from .cache_strategies import RedisCache, LocalCache
from config import CacheConfig
from threading import Lock
from src.utils.logging import get_logger
from .cache_metrics import CacheMetrics

logger = get_logger("cache")

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

            settings = Cache._settings or {"mode": CacheConfig.CACHE_LOCAL, "enabled": True}
            
            if not settings.get("enabled", True):
                Cache._instance = None
                return None
            
            if Cache._cache_metrics is None:
                Cache._cache_metrics = CacheMetrics()

            mode = settings.get("mode", CacheConfig.CACHE_LOCAL)

            if mode == CacheConfig.CACHE_CLOUD:
                cache_obj = RedisCache(
                    host=CacheConfig.CLOUD_HOST,
                    port=CacheConfig.CLOUD_PORT,
                    password=CacheConfig.CLOUD_PASS,
                    mode=mode,
                    metrics=Cache._cache_metrics
                )
            elif mode == CacheConfig.CACHE_LOCAL:
                cache_obj = RedisCache(
                    host=CacheConfig.LOCAL_HOST,
                    port=CacheConfig.LOCAL_PORT,
                    password=CacheConfig.LOCAL_PASS,
                    mode=mode,
                    metrics=Cache._cache_metrics
                )
            elif mode == CacheConfig.CACHE_DICT:
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
