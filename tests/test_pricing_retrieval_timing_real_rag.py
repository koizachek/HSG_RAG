import os
import sys
from time import perf_counter

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import config
from src.database.weavservice import WeaviateService
from src.rag.agent_chain import ExecutiveAgentChain


pytestmark = [pytest.mark.network, pytest.mark.integration]


def _has_real_rag_prerequisites() -> tuple[bool, str]:
    if config.weaviate.LOCAL_DATABASE:
        return True, ""

    missing = []
    if not config.weaviate.CLUSTER_URL:
        missing.append("WEAVIATE_CLUSTER_URL")
    if not config.weaviate.WEAVIATE_API_KEY:
        missing.append("WEAVIATE_API_KEY")
    if not config.weaviate.HUGGING_FACE_API_KEY:
        missing.append("HUGGING_FACE_API_KEY")

    if missing:
        return False, f"Missing Weaviate configuration for real RAG timing test: {', '.join(missing)}"

    return True, ""


_READY, _SKIP_REASON = _has_real_rag_prerequisites()


@pytest.mark.skipif(not _READY, reason=_SKIP_REASON)
def test_real_rag_pricing_retrieval_timing_by_query():
    max_total_seconds = float(os.getenv("REAL_RAG_PRICING_MAX_TOTAL_SEC", "20"))
    max_retrieval_seconds = float(os.getenv("REAL_RAG_PRICING_MAX_RETRIEVAL_SEC", "8"))

    agent = object.__new__(ExecutiveAgentChain)
    try:
        agent._dbservice = WeaviateService()
    except Exception as exc:
        pytest.skip(f"Could not connect to Weaviate for real RAG timing test: {exc}")

    retrieval_timings = []
    original_retrieve = agent._retrieve_context_via_tool

    def timed_retrieve(query: str, program: str, language: str | None = None) -> str:
        started = perf_counter()
        context = original_retrieve(query=query, program=program, language=language)
        elapsed = perf_counter() - started
        retrieval_timings.append(
            {
                "program": program,
                "language": language,
                "elapsed_s": elapsed,
                "query": query,
                "context_chars": len(context or ""),
            }
        )
        return context

    agent._retrieve_context_via_tool = timed_retrieve

    cases = [
        ("de", "emba", "Was kostet das EMBA HSG Programm?"),
        ("en", "iemba", "What is the tuition for the IEMBA?"),
        ("en", "emba_x", "How much does emba X cost?"),
    ]

    started = perf_counter()
    responses = [
        agent._build_programme_fact_response(programme, language, query)
        for language, programme, query in cases
    ]
    total_elapsed = perf_counter() - started

    summary_lines = ["Real RAG pricing retrieval timing:"]
    for item in retrieval_timings:
        summary_lines.append(
            f"{item['program']} {item['language']} "
            f"{item['elapsed_s']:.3f}s context_chars={item['context_chars']} "
            f"query={item['query']}"
        )
    summary_lines.append(f"total: {total_elapsed:.3f}s")
    summary = "\n".join(summary_lines)
    print(f"\n{summary}")

    assert len(retrieval_timings) == len(cases), summary
    assert all("CHF" in response for response in responses), summary
    assert all(item["context_chars"] > 0 for item in retrieval_timings), summary
    assert max(item["elapsed_s"] for item in retrieval_timings) < max_retrieval_seconds, summary
    assert total_elapsed < max_total_seconds, summary
