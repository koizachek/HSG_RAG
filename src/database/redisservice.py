import os
import redis
from threading import Lock
from src.utils.logging import get_logger

logger = get_logger("redis_service")

class RedisService:
    _instance = None
    _init_lock = Lock()

    def __new__(cls, host, port, password, type):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host, port, password, type):
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._client = None
        self._host = host
        self._port = port
        self._password = password 
        self.type = type   
        
        self._connect()

        self._initialized = True

    def _connect(self):
        try:
            logger.info(f"Connecting to Redis at {self._host}:{self._port}...")
            self._client = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            self._client.ping()
            logger.info(f"Successfully connected to Redis! {self.type}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._client = None

    def get_client(self):
        return self._client
    
    def is_connected(self) -> bool:
        return self._client is not None