from dataclasses import dataclass
from threading import Lock


@dataclass
class CacheStatistics:
    hits: int
    misses: int
    hits_ratio: float

class CacheMetrics:
    def __init__(self) -> None:
        self.cache_stats = CacheStatistics(0, 0, 0.0)
        self._lock = Lock()
    
    def increment_hit(self):
        with self._lock:
            self.cache_stats.hits += 1
            self._calc_hit_ratio()
    
    def increment_miss(self):
        with self._lock:
            self.cache_stats.misses += 1
            self._calc_hit_ratio()

    def _calc_hit_ratio(self):
        total = self.cache_stats.hits + self.cache_stats.misses
        self.cache_stats.hits_ratio = (self.cache_stats.hits / total) if total else 0.0