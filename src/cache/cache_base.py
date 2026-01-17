from abc import ABC, abstractmethod

class CacheStrategy(ABC):
    """
    Defines the interface for the different cache system strategies (Local or Redis).
    """
    
    @abstractmethod
    def set(self, key: str, value: dict, language: str):
        pass

    @abstractmethod
    def get(self, key: str, language: str):
        pass

    @abstractmethod
    def clear_cache(self):
        pass
