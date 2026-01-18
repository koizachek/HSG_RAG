from .cache_strategies import RedisCache, LocalCache
from config import CacheConfig
from threading import Lock

class Cache:
    _instance = None
    _settings = None
    _lock = Lock()

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
            
            if Cache._settings is None:
                Cache._settings = {"mode": "local", "enabled": True}

            if not Cache._settings["enabled"]:
                return None

            if Cache._settings["mode"] == "cloud":
                cache = RedisCache(host=CacheConfig.CLOUD_HOST, port=CacheConfig.CLOUD_PORT, password=CacheConfig.CLOUD_PASS, type="cloud")
            else:
                cache = RedisCache(host=CacheConfig.LOCAL_HOST, port=CacheConfig.LOCAL_PORT, password="", type="local")

            if cache.client is None:
                Cache._instance = LocalCache()
            else:
                Cache._instance = cache

        return Cache._instance