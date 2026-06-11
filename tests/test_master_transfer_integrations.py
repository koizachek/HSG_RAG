from threading import RLock
from types import SimpleNamespace

from src.database.weavservice import WeaviateService
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.models import ModelConfigurator
from src.config import config


class FakeDbService:
    def __init__(self):
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)

        doc = SimpleNamespace(
            properties={
                "body": "emba X context",
                "programs": ["emba_x"],
                "source": "fake-source",
            }
        )
        return SimpleNamespace(objects=[doc]), 0.01


def test_retrieve_context_filters_embax_with_canonical_programme_id():
    agent = object.__new__(ExecutiveAgentChain)
    agent._initial_language = "en"
    agent._dbservice = FakeDbService()

    result = agent._retrieve_context("admissions requirements", "emba X", "en")

    assert "emba X context" in result
    assert agent._dbservice.calls[0]["property_filters"] == {"programs": ["emba_x"]}


class FakeQuery:
    def __init__(self):
        self.hybrid_calls = []

    def hybrid(self, **kwargs):
        self.hybrid_calls.append(kwargs)
        return SimpleNamespace(objects=[])


class FakeCollections:
    def __init__(self, collection):
        self.collection = collection

    def exists(self, name):
        self.exists_name = name
        return True

    def get(self, name):
        self.get_name = name
        return self.collection


def test_weaviate_keep_warm_once_runs_hybrid_warmup():
    collection = SimpleNamespace(query=FakeQuery())
    client = SimpleNamespace(collections=FakeCollections(collection))
    service = object.__new__(WeaviateService)
    service._client = client
    service._client_lock = RLock()
    service._last_query_time = 0
    service._keep_warm_interval = 1

    assert service._keep_warm_once() is True
    assert collection.query.hybrid_calls[0]["query"] == "HSG"
    assert collection.query.hybrid_calls[0]["limit"] == 1


def test_model_config_keeps_master_defaults_and_budgets(monkeypatch):
    calls = []

    def fake_initialize_model(cls, provider, model, role="main"):
        calls.append((provider, model, role))
        return object()

    monkeypatch.setattr(ModelConfigurator, "_initialize_model", classmethod(fake_initialize_model))
    ModelConfigurator._main_model_instance = None
    ModelConfigurator._language_detector_model_instance = None
    ModelConfigurator._confidence_scoring_model_instance = None
    ModelConfigurator._fallback_models_instances = None

    ModelConfigurator.get_main_agent_model()
    ModelConfigurator.get_language_detector_model()
    ModelConfigurator.get_confidence_scoring_model()
    ModelConfigurator.get_fallback_models()

    assert config.llm.MAIN_AGENT_MODEL == ("openai", "gpt-4.1")
    assert config.llm.FALLBACK_MODELS == [("openai", "gpt-5-mini")]
    assert config.llm.get_default_model() == "gpt-4.1"
    assert config.llm.get_fallback_models()[0][1] == "gpt-5-mini"
    assert ModelConfigurator._openai_budget("main") == {
        "max_tokens": 3072,
        "timeout": 30,
        "request_timeout": 30,
    }
    assert ModelConfigurator._openai_budget("language_detector") == {
        "max_tokens": 64,
        "timeout": 10,
        "request_timeout": 10,
    }
    assert ("openai", "gpt-4.1", "main") in calls
    assert ("openai", "gpt-4o-mini", "language_detector") in calls
    assert ("openai", "gpt-4o-mini", "confidence_scoring") in calls
