import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cache.cache import Cache
from src.config import config
from src.rag.agent_chain import ExecutiveAgentChain


pytestmark = [pytest.mark.network, pytest.mark.integration]


def _has_real_agent_prerequisites() -> tuple[bool, str]:
    llm_api_key = config.llm.get_api_key()
    if not llm_api_key:
        return False, "No LLM API key configured for the real agent positioning test."

    missing = []
    if not config.weaviate.CLUSTER_URL:
        missing.append("WEAVIATE_CLUSTER_URL")
    if not config.weaviate.WEAVIATE_API_KEY:
        missing.append("WEAVIATE_API_KEY")
    if not config.processing.EMBEDDING_API_KEY:
        missing.append("OPEN_ROUTER_API_KEY")

    if missing:
        return False, f"Missing Weaviate configuration for real agent positioning test: {', '.join(missing)}"

    return True, ""


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    normalized = _normalize(text)
    return sum(1 for keyword in keywords if keyword.lower() in normalized)


_READY, _SKIP_REASON = _has_real_agent_prerequisites()


@pytest.fixture
def real_agent_positioning():
    old_cache_enabled = config.cache.ENABLED
    old_cache_settings = Cache._settings
    old_cache_instance = Cache._instance

    Cache.configure(mode="dict", cache=False)
    Cache._instance = None

    try:
        yield ExecutiveAgentChain(
            language="en",
            session_id=f"programme-positioning-{uuid.uuid4()}",
        )
    finally:
        config.cache.ENABLED = old_cache_enabled
        Cache._settings = old_cache_settings
        Cache._instance = old_cache_instance


@pytest.mark.skipif(not _READY, reason=_SKIP_REASON)
def test_generic_programme_comparison_stays_balanced(real_agent_positioning):
    response = real_agent_positioning.query(
        "What is the difference between EMBA HSG and IEMBA HSG?"
    )
    response_text = _normalize(response.response)

    assert "emba hsg" in response_text
    assert "iemba" in response_text
    assert response.appointment_requested is False
    assert response.show_booking_widget is False
    assert "best" not in response_text
    assert "perfect" not in response_text
    assert "guaranteed" not in response_text
    assert "world-class" not in response_text


@pytest.mark.skipif(not _READY, reason=_SKIP_REASON)
def test_emba_interest_triggers_positive_value_framing(real_agent_positioning):
    real_agent_positioning.query("I am particularly interested in the EMBA HSG.")
    response = real_agent_positioning.query(
        "Why might this programme be attractive for a German-speaking leader in the DACH region?"
    )

    emba_keywords = [
        "dach",
        "german-speaking",
        "general management",
        "leadership",
        "peer network",
        "regional",
    ]
    response_text = response.response

    assert "EMBA HSG" in response_text or "EMBA" in response_text
    assert _count_keyword_hits(response_text, emba_keywords) >= 2, response_text
    assert "best" not in _normalize(response_text)
    assert "perfect" not in _normalize(response_text)
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


@pytest.mark.skipif(not _READY, reason=_SKIP_REASON)
def test_iemba_interest_triggers_positive_value_framing(real_agent_positioning):
    real_agent_positioning.query("I am particularly interested in the IEMBA HSG.")
    response = real_agent_positioning.query(
        "Why might this programme be attractive for an executive with international ambitions?"
    )

    iemba_keywords = [
        "international",
        "global",
        "cohort",
        "cross-cultural",
        "different business environments",
        "exposure",
    ]
    response_text = response.response

    assert "IEMBA" in response_text
    assert _count_keyword_hits(response_text, iemba_keywords) >= 2, response_text
    assert "best" not in _normalize(response_text)
    assert "perfect" not in _normalize(response_text)
    assert response.appointment_requested is False
    assert response.show_booking_widget is False
