import os
import sys
import uuid
from time import perf_counter

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cache.cache import Cache
from src.config import config
from src.rag.agent_chain import ExecutiveAgentChain


pytestmark = [pytest.mark.network, pytest.mark.integration]


def _has_real_agent_prerequisites() -> tuple[bool, str]:
    if not any([
        config.llm.OPENAI_API_KEY, 
        config.llm.OPENROUTER_API_KEY, 
        config.llm.HUGGING_FACE_API_KEY,
        config.llm.GROQ_API_KEY,
    ]):
        return False, "No LLM API key configured for the real agent test."

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
        return False, f"Missing Weaviate configuration for real agent test: {', '.join(missing)}"

    return True, ""


_READY, _SKIP_REASON = _has_real_agent_prerequisites()


@pytest.mark.skipif(not _READY, reason=_SKIP_REASON)
def test_reply_speed_sample_conversation_real_agent():
    old_cache_enabled = config.cache.ENABLED
    old_cache_settings = Cache._settings
    old_cache_instance = Cache._instance

    Cache.configure(mode="dict", cache=False)
    Cache._instance = None

    max_turn_seconds = float(os.getenv("REAL_REPLY_SPEED_MAX_TURN_SEC", "45"))
    max_total_seconds = float(os.getenv("REAL_REPLY_SPEED_MAX_TOTAL_SEC", "150"))

    conversation = [
        "Was kostet das EMBA HSG Programm?",
        "Ich möchte einen Termin für das EMBA HSG buchen.",
        "Bitte zeigen Sie mir verfügbare Online-Termine am Wochenanfang vormittags.",
    ]

    timings = []

    try:
        agent = ExecutiveAgentChain(
            language="de",
            session_id=f"real-reply-speed-{uuid.uuid4()}",
        )

        total_start = perf_counter()
        responses = []
        for turn in conversation:
            turn_start = perf_counter()
            response = agent.query(turn)
            elapsed = perf_counter() - turn_start
            responses.append(response)
            timings.append(
                {
                    "query": turn,
                    "elapsed_s": elapsed,
                    "language": response.language,
                    "show_booking_widget": response.show_booking_widget,
                    "appointment_requested": response.appointment_requested,
                    "response_preview": response.response[:140].replace("\n", " "),
                }
            )
        total_elapsed = perf_counter() - total_start

    finally:
        config.cache.ENABLED = old_cache_enabled
        Cache._settings = old_cache_settings
        Cache._instance = old_cache_instance

    summary_lines = ["Real agent reply speed summary:"]
    for idx, timing in enumerate(timings, start=1):
        summary_lines.append(
            f"turn {idx}: {timing['elapsed_s']:.3f}s | "
            f"lang={timing['language']} | "
            f"widget={timing['show_booking_widget']} | "
            f"appointment={timing['appointment_requested']} | "
            f"query={timing['query']} | "
            f"preview={timing['response_preview']}"
        )
    summary_lines.append(f"total: {total_elapsed:.3f}s")
    summary = "\n".join(summary_lines)
    print(f"\n{summary}")

    for response in responses:
        assert response.response.strip(), summary

    assert responses[0].language == "de", summary
    assert any(response.appointment_requested for response in responses[1:]), summary
    assert responses[-1].show_booking_widget is True, summary
    assert max(item["elapsed_s"] for item in timings) < max_turn_seconds, summary
    assert total_elapsed < max_total_seconds, summary
