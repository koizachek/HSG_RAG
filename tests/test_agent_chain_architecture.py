import uuid

from langchain_core.messages import HumanMessage

from src.cache.cache import Cache
from src.rag import agent_chain as agent_chain_module
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.programme_facts import ProgrammeFacts
from src.rag.tools.registry import AgentToolRegistry
from src.rag.utilclasses import LeadAgentQueryResponse, StructuredAgentResponse
from src.config import config


class DummyWeaviateService:
    def query(self, *args, **kwargs):
        class _DummyResponse:
            objects = []

        return _DummyResponse(), None


class FakeLanguageDetector:
    def detect_explicit_switch_request(self, query: str) -> str | None:
        return None

    def is_language_neutral_program_reference(self, query: str) -> bool:
        return False

    def detect_language(self, query: str) -> str:
        return "en"


class LongAnswerAgent:
    name = "lead_agent"

    def invoke(self, payload, config=None, context=None):
        response = " ".join(["detail"] * 180)
        return {
            "structured_response": StructuredAgentResponse(
                response=response,
                additional_details="Secondary dropdown context.",
                is_context_dependent=False,
            ),
            "messages": [type("FakeMessage", (), {"text": response})()],
        }


def _fake_init_agents(self):
    return {"lead": LongAnswerAgent()}, {"configurable": {"thread_id": 0}}


def test_response_contract_does_not_expose_booking_fields():
    structured = StructuredAgentResponse(response="Answer")
    lead = LeadAgentQueryResponse(response="Answer", language="en")

    for field in ("appointment_requested", "show_booking_widget", "relevant_programs"):
        assert not hasattr(structured, field)
        assert not hasattr(lead, field)


def test_query_lead_does_not_chunk_or_append_continuation(monkeypatch):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(agent_chain_module, "LanguageDetector", FakeLanguageDetector)
    monkeypatch.setattr(ExecutiveAgentChain, "_init_agents", _fake_init_agents)

    old_eval_quality = config.chain.EVALUATE_RESPONSE_QUALITY
    old_chunking = config.chain.ENABLE_RESPONSE_CHUNKING
    old_track_profile = config.convstate.TRACK_USER_PROFILE
    old_cache_enabled = config.cache.ENABLED
    old_cache_settings = Cache._settings
    old_cache_instance = Cache._instance

    config.chain.EVALUATE_RESPONSE_QUALITY = False
    config.chain.ENABLE_RESPONSE_CHUNKING = True
    config.convstate.TRACK_USER_PROFILE = False
    Cache._instance = None
    Cache.configure(mode="dict", cache=False)

    try:
        agent = ExecutiveAgentChain(language="en", session_id=f"chunk-test-{uuid.uuid4()}")
        response = agent.query("Give me a detailed comparison.")
    finally:
        config.chain.EVALUATE_RESPONSE_QUALITY = old_eval_quality
        config.chain.ENABLE_RESPONSE_CHUNKING = old_chunking
        config.convstate.TRACK_USER_PROFILE = old_track_profile
        config.cache.ENABLED = old_cache_enabled
        Cache._settings = old_cache_settings
        Cache._instance = old_cache_instance

    assert "Would you like me to continue" not in response.response
    assert response.additional_details == "Secondary dropdown context."
    assert agent._pending_continuation is None
    assert len(response.response.split()) == 180


def test_programme_facts_tool_is_structured_and_does_not_mutate_state():
    class FakeProvider:
        def __init__(self):
            self.calls = []

        def get_facts_many(self, programmes, language):
            self.calls.append((programmes, language))
            return {
                "emba": ProgrammeFacts(
                    programme="emba",
                    source_available=True,
                    structured={"tuition": "CHF 77'500"},
                    document_points=["CV and degree certificates"],
                )
            }

    provider = FakeProvider()
    registry = AgentToolRegistry(lambda *_args: "", provider)
    history = [HumanMessage("What does EMBA cost?")]

    result = registry.programme_facts_tool.invoke(
        {
            "programmes": ["EMBA HSG"],
            "fields": ["tuition", "documents"],
            "language": "de",
            "query": "Was kostet das EMBA HSG?",
        }
    )

    assert "CHF 77'500" in result
    assert "CV and degree certificates" in result
    assert provider.calls == [(["emba"], "de")]
    assert len(history) == 1
    assert history[0].content == "What does EMBA cost?"
