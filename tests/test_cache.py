import uuid
import pytest

from langchain_core.messages import HumanMessage, SystemMessage

from src.cache.cache import Cache
from src.rag.agent_chain import ExecutiveAgentChain as RealExecutiveAgentChain
from src.rag.utilclasses import StructuredAgentResponse
from src.utils.lang import get_language_name
from src.config import config
from src.rag import agent_chain as agent_chain_module


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
        return "de"


class FakeLeadAgent:
    name = "lead_agent"

    def invoke(self, payload, config=None, context=None):
        messages = payload["messages"]
        human_messages = [msg for msg in messages if getattr(msg, "type", None) == "human"]
        query = human_messages[-1].content if human_messages else ""
        query_lower = query.lower()

        is_context_dependent = any(
            marker in query_lower
            for marker in (
                "geeignet",
                "berufserfahrung",
                "fÃ¼hrungserfahrung",
                "tech-bereich",
                "passt",
            )
        )

        if "was ist das emba hsg" in query_lower:
            response_text = "Das EMBA HSG ist ein berufsbegleitendes Executive-MBA-Programm."
        elif "wann startet das iemba" in query_lower:
            response_text = "Das IEMBA startet einmal jÃ¤hrlich."
        elif "welches programm passt" in query_lower:
            response_text = "Auf Basis Ihrer Angaben passt wahrscheinlich das IEMBA besser."
        elif "geeignet" in query_lower:
            response_text = "FÃ¼r eine EignungseinschÃ¤tzung sind Ihre Erfahrung und FÃ¼hrungsverantwortung relevant."
        else:
            response_text = "Ich habe Ihre Angaben aufgenommen."

        response = StructuredAgentResponse(
            response=response_text,
            is_context_dependent=is_context_dependent,
        )

        return {
            "structured_response": response,
            "messages": [type("FakeMessage", (), {"text": response.response})()],
        }


def _fake_init_agents(self):
    return {"lead": FakeLeadAgent()}, {"configurable": {"thread_id": 0}}


def test_chain_context_dependency_and_cacheability_offline(monkeypatch):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(agent_chain_module, "LanguageDetector", FakeLanguageDetector)
    monkeypatch.setattr(RealExecutiveAgentChain, "_init_agents", _fake_init_agents)

    old_eval_quality = config.chain.EVALUATE_RESPONSE_QUALITY
    old_track_profile = config.convstate.TRACK_USER_PROFILE
    old_cache_enabled = config.cache.ENABLED
    old_cache_settings = Cache._settings
    old_cache_instance = Cache._instance

    config.chain.EVALUATE_RESPONSE_QUALITY = False
    config.convstate.TRACK_USER_PROFILE = False
    Cache._instance = None
    Cache.configure(mode="dict", cache=True)

    try:
        examples = [
            {
                "name": "static FAQ should be context-independent and cacheable",
                "query": "Was ist das EMBA HSG?",
                "expected_context_dependent": False,
                "expected_should_cache": True,
            },
            {
                "name": "programme fact should be context-independent and cacheable",
                "query": "Wann startet das IEMBA?",
                "expected_context_dependent": False,
                "expected_should_cache": True,
            },
            {
                "name": "eligibility question should be context-dependent and not cacheable",
                "query": "Bin ich mit 6 Jahren Berufserfahrung und 3 Jahren FÃ¼hrungserfahrung fÃ¼r das EMBA HSG geeignet?",
                "expected_context_dependent": True,
                "expected_should_cache": False,
            },
            {
                "name": "recommendation question should be context-dependent and not cacheable",
                "query": "Ich arbeite im Tech-Bereich. Welches Programm passt besser zu mir, IEMBA oder emba X?",
                "expected_context_dependent": True,
                "expected_should_cache": False,
            },
        ]

        for example in examples:
            # Agent instance for checking raw structured output
            raw_agent = RealExecutiveAgentChain(
                language="de",
                session_id=f"raw-{uuid.uuid4()}",
            )

            raw_messages = [
                HumanMessage(example["query"]),
                SystemMessage(f"Respond in {get_language_name('de')} language."),
            ]

            structured = raw_agent._query(
                agent=raw_agent._agents["lead"],
                messages=raw_messages,
                thread_id=f"test-{uuid.uuid4()}",
            )

            assert structured.is_context_dependent == example["expected_context_dependent"], (
                f"{example['name']}: expected is_context_dependent="
                f"{example['expected_context_dependent']}, got {structured.is_context_dependent}. "
                f"Response was: {structured.response}"
            )

            # Fresh agent instance for checking final should_cache behaviour
            final_agent = RealExecutiveAgentChain(
                language="de",
                session_id=f"final-{uuid.uuid4()}",
            )

            final = final_agent.query(example["query"])

            assert final.should_cache == example["expected_should_cache"], (
                f"{example['name']}: expected should_cache="
                f"{example['expected_should_cache']}, got {final.should_cache}. "
                f"Response was: {final.response}"
            )

        # Extra real history-based example:
        # follow-up after prior turns must be context-dependent / not cacheable
        history_agent = RealExecutiveAgentChain(
            language="de",
            session_id=f"history-{uuid.uuid4()}",
        )

        history_agent.query("Ich habe 8 Jahre Berufserfahrung, 4 Jahre FÃ¼hrungserfahrung und arbeite in der Softwarebranche.")

        followup_query = "Welches Programm passt zu mir?"
        followup_final = history_agent.query(followup_query)

        assert followup_final.should_cache is False, (
            "Follow-up recommendation based on prior turns must not be cacheable. "
            f"Response was: {followup_final.response}"
        )

    finally:
        config.chain.EVALUATE_RESPONSE_QUALITY = old_eval_quality
        config.convstate.TRACK_USER_PROFILE = old_track_profile
        config.cache.ENABLED = old_cache_enabled
        Cache._settings = old_cache_settings
        Cache._instance = old_cache_instance
