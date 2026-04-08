import time
import fakeredis
import pytest
import redis

from unittest.mock import patch, MagicMock
from src.database.redisservice import RedisService
from src.rag.utilclasses import LeadAgentQueryResponse
from src.cache.cache import Cache
from unittest.mock import MagicMock, patch
from src.cache.cache import Cache
from src.cache.cache_strategies import RedisCache, LocalCache
from src.config import config

class ExecutiveAgentChain:
    def preprocess_query(self, message: str):
        return LeadAgentQueryResponse(
            response=None,
            processed_query=message,
            language="de",
            should_cache=True,
            confidence_fallback=False,
            max_turns_reached=False,
        )

    def agent_query(self, query: str):
        return LeadAgentQueryResponse(
            response=f"Antwort auf: {query}",
            processed_query=query,
            language="de",
            should_cache=True,
            confidence_fallback=False,
            max_turns_reached=False,
        )

class ChatBotApplication:
    def __init__(self):
        self._cache = Cache.get_cache()
        self._language = "de"

    def _chat(self, message: str, agent: ExecutiveAgentChain):
        preprocess_resp = agent.preprocess_query(message)
        current_lang = preprocess_resp.language
        processed_q = preprocess_resp.processed_query

        final_response = None

        if preprocess_resp.response is not None:
            final_response = preprocess_resp

        elif Cache._settings["enabled"]:
            cached_text = self._cache.get(processed_q, language=current_lang)
            if cached_text is not None:
                final_response = LeadAgentQueryResponse(
                    response=cached_text,
                    processed_query=processed_q,
                    language=current_lang,
                    should_cache=False,
                    confidence_fallback=False,
                    max_turns_reached=False,
                )

        if final_response is None:
            final_response = agent.agent_query(processed_q)

        if final_response.should_cache and Cache._settings["enabled"]:
            self._cache.set(
                key=processed_q,
                value=final_response.response,
                language=current_lang
            )

        return final_response.response

########################################### Tests dict cache strategy ###########################################
def test_local_cache_hit():
    Cache.configure(mode="dict", no_cache=False)
    
    app = ChatBotApplication()
    agent = ExecutiveAgentChain()

    r1 = app._chat("Was ist EMBA?", agent)
    r2 = app._chat("Was ist EMBA?", agent)

    assert r1 == "Antwort auf: Was ist EMBA?"
    assert r2 == "Antwort auf: Was ist EMBA?"

    stats = Cache._cache_metrics.cache_stats
    assert stats.misses == 1
    assert stats.hits == 1   

def test_local_cache_miss():
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None
    
    Cache.configure(mode="dict", no_cache=False)
    
    app = ChatBotApplication()
    agent = ExecutiveAgentChain()
    
    r1 = app._chat("Was ist EMBA?", agent)
    r2 = app._chat("Was ist IEMBA?", agent)

    assert r1 == "Antwort auf: Was ist EMBA?"
    assert r2 == "Antwort auf: Was ist IEMBA?"

    stats = Cache._cache_metrics.cache_stats
    assert stats.misses == 2
    assert stats.hits == 0

def test_local_cache_generate_normalized_key():
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None
    
    Cache.configure(mode="dict", no_cache=False)
    
    app = ChatBotApplication()
    
    normalized_key = app._cache._generate_normalized_key("Was ist EMBA?", "de")
    
    assert normalized_key == "cache:de:wasistemba"

def test_local_cache_max_size(monkeypatch):
    monkeypatch.setattr("src.config.config.cache.MAX_SIZE_CACHE", 2)

    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None
    
    Cache.configure(mode="dict", no_cache=False)
    app = ChatBotApplication()
    cache = app._cache
    agent = ExecutiveAgentChain()
    
    app._chat("Was ist EMBA?", agent)
    app._chat("Was ist IEMBA?", agent)
    app._chat("Was ist EMBAX?", agent)
    app._chat("Was ist EMBA?", agent)

    stats = Cache._cache_metrics.cache_stats
    assert stats.misses == 4
    assert stats.hits == 0   
    assert len(cache.cache) == 2

def test_local_cache_ttl_expiry(monkeypatch):
    monkeypatch.setattr("src.config.config.cache.TTL_CACHE", 1)

    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None
    
    Cache.configure(mode="dict", no_cache=False)
    app = ChatBotApplication()
    cache = app._cache
    agent = ExecutiveAgentChain()
    
    stats = Cache._cache_metrics.cache_stats
    
    app._chat("Was ist EMBA?", agent)
    time.sleep(1.2)
    
    assert len(cache.cache) == 0
    app._chat("Was ist EMBA?", agent)
    assert stats.misses == 2
    assert stats.hits == 0

def test_redis_connection_failure_on_startup_falls_back_to_local_cache():
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=None):
        Cache.configure(mode="local", no_cache=False)
        cache = Cache.get_cache()

        assert isinstance(cache, LocalCache)

########################################################### Test Cache with Redis (using fakeredis) ###########################################################
def test_cache_uses_redis_with_fakeredis():
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None

    fake_redis = fakeredis.FakeRedis()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_redis):
        Cache.configure(mode="local", no_cache=False)
        cache = Cache.get_cache()

        assert isinstance(cache, RedisCache)

def test_redis_cache_hit_with_fakeredis():
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None

    fake_redis = fakeredis.FakeRedis()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_redis):
        Cache.configure(mode="local", no_cache=False)
        app = ChatBotApplication()
        agent = ExecutiveAgentChain()

        r1 = app._chat("Was ist EMBA?", agent)
        r2 = app._chat("Was ist EMBA?", agent)

        assert r1 == "Antwort auf: Was ist EMBA?"
        assert r2 == "Antwort auf: Was ist EMBA?"

        stats = Cache._cache_metrics.cache_stats
        assert stats.misses == 1
        assert stats.hits == 1

def test_redis_cache_miss_with_fakeredis():
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None

    fake_redis = fakeredis.FakeRedis()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_redis):
        Cache.configure(mode="local", no_cache=False)
        app = ChatBotApplication()
        agent = ExecutiveAgentChain()

        r1 = app._chat("Was ist EMBA?", agent)
        r2 = app._chat("Was ist IEMBA?", agent)

        assert r1 == "Antwort auf: Was ist EMBA?"
        assert r2 == "Antwort auf: Was ist IEMBA?"

        stats = Cache._cache_metrics.cache_stats
        assert stats.misses == 2
        assert stats.hits == 0

def test_redis_cache_generate_normalized_key():
    fake_redis = fakeredis.FakeRedis()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_redis):
        cache = RedisCache(
            host="localhost",
            port=6379,
            password="",
            mode="local",
            metrics=MagicMock()
        )

        normalized_key = cache._generate_normalized_key("Was ist EMBA?", "de")

        assert normalized_key == "cache:de:wasistemba"

def test_redis_cache_ttl_expiry_with_fakeredis(monkeypatch):
    Cache._instance = None
    Cache._settings = None
    Cache._cache_metrics = None

    monkeypatch.setattr(config.cache, "TTL_CACHE", 1)

    fake_redis = fakeredis.FakeRedis()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_redis):
        Cache.configure(mode="local", no_cache=False)
        app = ChatBotApplication()
        agent = ExecutiveAgentChain()

        app._chat("Was ist EMBA?", agent)
        time.sleep(1.2)
        app._chat("Was ist EMBA?", agent)

        stats = Cache._cache_metrics.cache_stats
        assert stats.misses == 2
        assert stats.hits == 0

def test_redis_cache_clear_cache_with_fakeredis():
    fake_redis = fakeredis.FakeRedis()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_redis):
        cache = RedisCache(
            host="localhost",
            port=6379,
            password="",
            mode="local",
            metrics=MagicMock()
        )

        cache.set("Was ist EMBA?", "Antwort", "de")
        assert cache.get("Was ist EMBA?", "de") == "Antwort"

        cache.clear_cache()

        assert cache.get("Was ist EMBA?", "de") is None

def test_redis_ttl_set_correctly():
    fake_client = MagicMock()

    with patch("src.cache.cache_strategies.RedisService.get_client", return_value=fake_client):
        cache = RedisCache(
            host="localhost",
            port=6379,
            password="",
            mode="local",
            metrics=MagicMock()
        )

        cache.set("Was ist EMBA?", "Antwort", "de")

        fake_client.set.assert_called_once_with(
            "cache:de:wasistemba",
            '"Antwort"',
            ex=config.cache.TTL_CACHE
        )