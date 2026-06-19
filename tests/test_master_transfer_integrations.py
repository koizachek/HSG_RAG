from threading import RLock
from types import SimpleNamespace

import pytest

from src.database.embeddings import EmbeddingError
from src.database import weavservice
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
        self.bm25_calls = []

    def hybrid(self, **kwargs):
        self.hybrid_calls.append(kwargs)
        return SimpleNamespace(objects=[])

    def bm25(self, **kwargs):
        self.bm25_calls.append(kwargs)
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


class FakeEmbeddingClient:
    def __init__(self, vector=None, fail=False):
        self.vector = vector or [0.1, 0.2, 0.3]
        self.fail = fail
        self.document_inputs = []
        self.query_inputs = []

    def embed_documents(self, texts):
        self.document_inputs.append(list(texts))
        if self.fail:
            raise EmbeddingError("embedding service unavailable")
        return [self.vector for _ in self.document_inputs[-1]]

    def embed_query(self, text):
        self.query_inputs.append(text)
        if self.fail:
            raise EmbeddingError("embedding service unavailable")
        return self.vector


def test_weaviate_keep_warm_once_runs_hybrid_warmup():
    collection = SimpleNamespace(query=FakeQuery())
    client = SimpleNamespace(collections=FakeCollections(collection))
    service = object.__new__(WeaviateService)
    service._client = client
    service._client_lock = RLock()
    service._last_query_time = 0
    service._keep_warm_interval = 1
    service._embedding_client = FakeEmbeddingClient(vector=[0.4, 0.5, 0.6])

    assert service._keep_warm_once() is True
    assert collection.query.hybrid_calls[0]["query"] == "HSG"
    assert collection.query.hybrid_calls[0]["limit"] == 1
    assert collection.query.hybrid_calls[0]["vector"] == [0.4, 0.5, 0.6]
    assert collection.query.hybrid_calls[0]["target_vector"] == config.processing.EMBEDDING_VECTOR_NAME


def test_embedding_config_defaults_to_openrouter_small_model():
    assert config.processing.EMBEDDING_MODEL == "openai/text-embedding-3-small"
    assert config.processing.EMBEDDING_BASE_URL == "https://openrouter.ai/api/v1"
    assert config.processing.EMBEDDING_DIMENSIONS == 1536
    assert config.processing.EMBEDDING_BATCH_SIZE == 32
    assert config.processing.MAX_TOKENS == 512


def test_processor_uses_embedding_model_tokenizer(monkeypatch):
    processors = pytest.importorskip("src.pipeline.processors")
    calls = []

    class FakeEncoding:
        def encode(self, text, **kwargs):
            return [1, 2]

        def decode(self, tokens):
            return "decoded"

    class FakeHybridChunker:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(
        processors.tiktoken,
        "encoding_for_model",
        lambda model: calls.append(model) or FakeEncoding(),
    )
    monkeypatch.setattr(processors, "HybridChunker", FakeHybridChunker)
    monkeypatch.setattr(processors, "EnhansedSerializerProvider", lambda: object())

    processor = object.__new__(processors.ProcessorBase)
    processor._chunker_instance = None

    chunker = processors.ProcessorBase._chunker.fget(processor)

    assert calls == ["text-embedding-3-small"]
    assert chunker.kwargs["max_tokens"] == config.processing.MAX_TOKENS
    assert chunker.kwargs["tokenizer"].count_tokens("test") == 2


def test_weaviate_vector_config_uses_self_provided_for_openrouter(monkeypatch):
    monkeypatch.setattr(config.processing, "EMBEDDING_VECTOR_NAME", "test_vectors")
    monkeypatch.setattr(
        weavservice.Configure.Vectors,
        "self_provided",
        lambda name: ("self_provided", name),
    )

    service = object.__new__(WeaviateService)

    assert service._vector_config() == ("self_provided", "test_vectors")


class FakeBatchContext:
    def __init__(self):
        self.added = []
        self.number_errors = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add_object(self, properties, vector=None, uuid=None):
        self.added.append({"properties": properties, "vector": vector, "uuid": uuid})


class FakeBatchFactory:
    def __init__(self, context):
        self.context = context

    def fixed_size(self, **kwargs):
        self.kwargs = kwargs
        return self.context


def test_batch_import_embeds_rows_and_writes_named_vectors(monkeypatch):
    monkeypatch.setattr(config.processing, "EMBEDDING_VECTOR_NAME", "test_vectors")
    batch_context = FakeBatchContext()
    collection = SimpleNamespace(batch=FakeBatchFactory(batch_context))
    service = object.__new__(WeaviateService)
    service._client_lock = RLock()
    service._last_query_time = 0
    service._embedding_client = FakeEmbeddingClient(vector=[0.7, 0.8, 0.9])
    service._select_collection = lambda lang: (collection, "test_collection")

    errors = service.batch_import(
        data_rows=[{"chunk_id": "c1", "body": "First chunk"}],
        lang="en",
    )

    assert errors == []
    assert service._embedding_client.document_inputs == [["First chunk"]]
    assert batch_context.added[0]["vector"] == {"test_vectors": [0.7, 0.8, 0.9]}
    assert batch_context.added[0]["uuid"]


def test_query_embeds_once_and_passes_vector_to_hybrid(monkeypatch):
    monkeypatch.setattr(config.processing, "EMBEDDING_VECTOR_NAME", "test_vectors")
    collection = SimpleNamespace(query=FakeQuery())
    service = object.__new__(WeaviateService)
    service._client_lock = RLock()
    service._last_query_time = 0
    service._embedding_client = FakeEmbeddingClient(vector=[0.2, 0.3, 0.4])
    service._select_collection = lambda lang: (collection, "test_collection")

    service.query(query="admissions", lang="en", limit=3)

    assert service._embedding_client.query_inputs == ["admissions"]
    assert collection.query.hybrid_calls[0]["vector"] == [0.2, 0.3, 0.4]
    assert collection.query.hybrid_calls[0]["target_vector"] == "test_vectors"
    assert collection.query.hybrid_calls[0]["limit"] == 3


def test_query_falls_back_to_bm25_when_embedding_fails(monkeypatch):
    collection = SimpleNamespace(query=FakeQuery())
    service = object.__new__(WeaviateService)
    service._client_lock = RLock()
    service._last_query_time = 0
    service._embedding_client = FakeEmbeddingClient(fail=True)
    service._select_collection = lambda lang: (collection, "test_collection")

    service.query(query="admissions", lang="en", limit=3)

    assert collection.query.hybrid_calls == []
    assert collection.query.bm25_calls[0]["query"] == "admissions"
    assert collection.query.bm25_calls[0]["limit"] == 3


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
