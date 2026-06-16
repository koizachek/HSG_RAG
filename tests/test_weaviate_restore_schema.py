import pytest

from src.config import config
from src.database.weavservice import WeaviateService


def test_restore_schema_uses_configured_replication_factor(monkeypatch):
    monkeypatch.setattr(config.weaviate, "REPLICATION_FACTOR", 3)
    service = object.__new__(WeaviateService)
    cfg = {
        "class": "hsg_rag_content_en",
        "replicationConfig": {
            "factor": 1,
            "deletionStrategy": "TimeBasedResolution",
        },
    }

    normalized = service._schema_config_for_restore(cfg)

    assert normalized["replicationConfig"]["factor"] == 3
    assert normalized["replicationConfig"]["deletionStrategy"] == "TimeBasedResolution"
    assert cfg["replicationConfig"]["factor"] == 1


def test_restore_schema_adds_missing_replication_config(monkeypatch):
    monkeypatch.setattr(config.weaviate, "REPLICATION_FACTOR", 3)
    service = object.__new__(WeaviateService)

    normalized = service._schema_config_for_restore({"class": "hsg_rag_content_de"})

    assert normalized["replicationConfig"]["factor"] == 3


def test_replication_factor_must_be_positive(monkeypatch):
    monkeypatch.setattr(config.weaviate, "REPLICATION_FACTOR", 0)
    service = object.__new__(WeaviateService)

    with pytest.raises(ValueError, match="WEAVIATE_REPLICATION_FACTOR"):
        service._schema_config_for_restore({"class": "hsg_rag_content_en"})
