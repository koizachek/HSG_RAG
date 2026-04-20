import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag import agent_chain as agent_chain_module
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.utilclasses import StructuredAgentResponse


class DummyWeaviateService:
    def query(self, *args, **kwargs):
        class _DummyResponse:
            objects = []

        return _DummyResponse(), None


class FakeLanguageDetector:
    def detect_explicit_switch_request(self, query: str) -> str | None:
        return None

    def is_language_neutral_program_reference(self, query: str) -> bool:
        return query.strip().casefold() in {
            "emba",
            "emba hsg",
            "iemba",
            "iemba hsg",
            "emba x",
            "embax",
        }

    def detect_language(self, query: str) -> str:
        query_lower = query.lower()
        if any(token in query_lower for token in ("was", "kostet", "studiengebühr", "programm")):
            return "de"
        return "en"


class FakeLeadAgent:
    name = "lead_agent"

    def invoke(self, payload, config=None, context=None):
        messages = payload["messages"]
        human_messages = [msg for msg in messages if getattr(msg, "type", None) == "human"]
        query = human_messages[-1].content if human_messages else ""
        query_lower = query.lower()

        if query_lower.strip() == "emba":
            response = StructuredAgentResponse(
                response=(
                    "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**. "
                    "In den Studiengebühren enthalten sind Kursunterlagen sowie die meisten "
                    "Mahlzeiten und Erfrischungen vor Ort. Unterkunft und Reisen sind nicht enthalten."
                ),
                appointment_requested=True,
                relevant_programs=["emba"],
            )
        elif "was kostet der emba" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Meinen Sie den deutschsprachigen **EMBA HSG**, den **International EMBA (IEMBA)** "
                    "oder das **emba X** Programm?"
                ),
                appointment_requested=False,
                relevant_programs=[],
            )
        elif "emba hsg" in query_lower and "iemba" not in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**. "
                    "In den Studiengebühren enthalten sind Kursunterlagen sowie die meisten "
                    "Mahlzeiten und Erfrischungen vor Ort. Unterkunft und Reisen sind nicht enthalten."
                ),
                appointment_requested=True,
                relevant_programs=["emba"],
            )
        elif "iemba" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "The tuition for the **IEMBA HSG** is **CHF 85,000**. "
                    "Included are course materials and most on-site meals and refreshments. "
                    "Accommodation and travel are not included."
                ),
                appointment_requested=True,
                relevant_programs=["iemba"],
            )
        elif "emba x" in query_lower or "embax" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "The tuition for **emba X** is **CHF 99,000** by the first application deadline "
                    "of **31 August 2026** and **CHF 110,000** by the final application deadline of "
                    "**31 October 2026**. Accommodation and travel are not included."
                ),
                appointment_requested=True,
                relevant_programs=["emba_x"],
            )
        elif "how much does the emba cost" in query_lower or "was kostet das emba programm" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Are you interested in the **German-speaking EMBA HSG**, the "
                    "**International EMBA (IEMBA)**, or the **emba X**?"
                ),
                appointment_requested=False,
                relevant_programs=[],
            )
        else:
            response = StructuredAgentResponse(
                response="Please specify which programme you mean.",
                appointment_requested=False,
                relevant_programs=[],
            )

        return {
            "structured_response": response,
            "messages": [type("FakeMessage", (), {"text": response.response})()],
        }


def _fake_init_agents(self):
    agents = {
        "lead": FakeLeadAgent(),
        "emba": FakeLeadAgent(),
        "iemba": FakeLeadAgent(),
        "embax": FakeLeadAgent(),
    }
    return agents, {"configurable": {"thread_id": 0}}


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(agent_chain_module, "LanguageDetector", FakeLanguageDetector)
    monkeypatch.setattr(ExecutiveAgentChain, "_init_agents", _fake_init_agents)
    monkeypatch.setattr(agent_chain_module.config.chain, "EVALUATE_RESPONSE_QUALITY", False, raising=False)
    monkeypatch.setattr(agent_chain_module.config.chain, "ENABLE_RESPONSE_CHUNKING", False, raising=False)
    return ExecutiveAgentChain(language="en")


def test_offline_smoke_emba_pricing_in_german(offline_agent):
    preprocessed = offline_agent.preprocess_query("Was kostet das EMBA HSG Programm?")
    response = offline_agent.agent_query(preprocessed.processed_query)

    assert preprocessed.language == "de"
    assert "CHF 77,500" in response.response
    assert "Unterkunft und Reisen sind nicht enthalten" in response.response
    assert response.appointment_requested is True
    assert response.relevant_programs == ["emba"]


def test_offline_smoke_iemba_pricing_in_english(offline_agent):
    preprocessed = offline_agent.preprocess_query("What is the tuition for the IEMBA?")
    response = offline_agent.agent_query(preprocessed.processed_query)

    assert preprocessed.language == "en"
    assert "CHF 85,000" in response.response
    assert "Accommodation and travel are not included" in response.response
    assert response.appointment_requested is True
    assert response.relevant_programs == ["iemba"]


def test_offline_smoke_embax_pricing_with_deadlines(offline_agent):
    preprocessed = offline_agent.preprocess_query("How much does emba X cost?")
    response = offline_agent.agent_query(preprocessed.processed_query)

    assert preprocessed.language == "en"
    assert "CHF 99,000" in response.response
    assert "31 August 2026" in response.response
    assert "CHF 110,000" in response.response
    assert "31 October 2026" in response.response
    assert response.appointment_requested is True
    assert response.relevant_programs == ["emba_x"]


def test_offline_smoke_ambiguous_pricing_question_requests_clarification(offline_agent):
    preprocessed = offline_agent.preprocess_query("How much does the EMBA cost?")
    response = offline_agent.agent_query(preprocessed.processed_query)

    assert "German-speaking EMBA HSG" in response.response
    assert "International EMBA (IEMBA)" in response.response
    assert "emba X" in response.response
    assert response.appointment_requested is False
    assert response.relevant_programs == []


def test_offline_smoke_program_name_follow_up_keeps_previous_language(offline_agent):
    first_turn = offline_agent.preprocess_query("Was kostet der EMBA?")
    first_response = offline_agent.agent_query(first_turn.processed_query)

    assert first_turn.language == "de"
    assert "Meinen Sie" in first_response.response

    second_turn = offline_agent.preprocess_query("EMBA")
    second_response = offline_agent.agent_query(second_turn.processed_query)

    assert second_turn.language == "de"
    assert offline_agent._stored_language == "de"
    assert "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**." in second_response.response
