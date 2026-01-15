from abc import ABC, abstractmethod

class CacheStrategy(ABC):
    """
    Defines the interface for the different cache system strategies (Local or Redis).
    """
    
    @abstractmethod
    def get(self, key):
        pass

    @abstractmethod
    def set(self, key, value):
        pass

    @abstractmethod
    def exists(self, key) -> bool:
        pass

    @abstractmethod
    def clear_cache(self):
        pass