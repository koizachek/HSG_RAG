import pytest

from src.const.agent_response_constants import (
    LANGUAGE_CLARIFICATION_MESSAGE,
    LANGUAGE_FALLBACK_MESSAGE,
)
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.input_handler import InputHandler
from src.rag.language_detection import LanguageDetector
from src.rag.scope_guardian import ScopeGuardian


def _agent_for_language_preprocessing(language: str = "en") -> ExecutiveAgentChain:
    agent = object.__new__(ExecutiveAgentChain)
    agent._stored_language = language
    agent._conversation_history = []
    agent._pending_continuation = None
    agent._input_handler = InputHandler()
    agent._scope_guardian = ScopeGuardian()
    agent._language_detector = LanguageDetector()
    agent._scope_violation_counts = {}
    agent._aggressive_violation_count = 0
    agent._invalid_input_count = 0
    agent._conversation_state = {
        "session_id": "session-1",
        "user_id": "session-1",
        "user_language": None,
        "user_name": None,
        "experience_years": None,
        "leadership_years": None,
        "field": None,
        "interest": None,
        "qualification_level": None,
        "program_interest": [],
        "suggested_program": None,
        "handover_requested": None,
        "topics_discussed": [],
        "preferences_known": False,
    }
    return agent


class TestQueryLanguageDetection:
    def test_program_names_are_treated_as_language_neutral(self):
        detector = LanguageDetector()

        for query in ("EMBA", "IEMBA", "emba X", "EMBA HSG", "IEMBA HSG", "embax"):
            assert detector.is_language_neutral_program_reference(query)

    def test_supported_language_detection_is_local(self):
        queries = {
            "en": "Hello, im interested in the EMBA Program",
            "de": "Guten Tag, ich interessiere mich fuer das EMBA Programm",
        }

        detector = LanguageDetector()
        for language, query in queries.items():
            assert detector.detect_language(query) == language
            assert detector._model is None

    def test_unsupported_language_returns_empty_without_llm(self):
        detector = LanguageDetector()

        assert detector.detect_language("Buenas tardes, quiero saber sobre el programa EMBA") == ""
        assert detector.detect_language("Bonjour, je souhaite en savoir plus sur le programme EMBA") == ""
        assert detector._model is None

    def test_mixed_language_input_needs_clarification(self):
        detector = LanguageDetector()

        assert detector.needs_language_clarification("Ich want to know sobre los programs")
        assert detector.detect_language("Ich want to know sobre los programs") == ""
        assert not detector.needs_language_clarification("I want to know about the programs")
        assert not detector.needs_language_clarification("I want to know about the Executive MBA")
        assert not detector.needs_language_clarification("Ich interessiere mich fuer die Programme")
        assert not detector.needs_language_clarification("Was sind die besten Restaurants in St. Gallen?")
        assert not detector.needs_language_clarification(
            "Buenas tardes, quiero saber sobre el programa EMBA"
        )

    def test_standalone_language_choice_is_explicit_switch(self):
        detector = LanguageDetector()

        assert detector.detect_explicit_switch_request("English") == "en"
        assert detector.detect_explicit_switch_request("Englisch") == "en"
        assert detector.detect_explicit_switch_request("Deutsch") == "de"
        assert detector.detect_explicit_switch_request("German") == "de"


def test_mixed_language_query_asks_user_to_choose_language():
    agent = _agent_for_language_preprocessing(language="en")

    response = agent.query("Ich want to know sobre los programs")

    assert response.response == LANGUAGE_CLARIFICATION_MESSAGE["de"]
    assert response.language == "de"
    assert "M\u00f6chten Sie auf Deutsch oder Englisch fortfahren?" in response.response
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_unsupported_language_query_uses_supported_language_fallback():
    agent = _agent_for_language_preprocessing(language="en")

    response = agent.query("Buenas tardes, quiero saber sobre el programa EMBA")

    assert response.response == LANGUAGE_FALLBACK_MESSAGE["en"]
    assert response.language == "en"
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
