import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.const.agent_response_constants import (
    LANGUAGE_CLARIFICATION_MESSAGE,
    LANGUAGE_FALLBACK_MESSAGE,
)
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.input_handler import InputHandler
from src.rag.language_detection import LanguageDetector
from src.rag.prompts import PromptConfigurator
from src.rag.scope_guardian import ScopeGuardian
from src.rag.utilclasses import LeadAgentQueryResponse


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
        assert detector.needs_language_clarification("Hello quiero saber sobre programs")
        assert detector.detect_language("Hello quiero saber sobre programs") == ""
        assert not detector.needs_language_clarification("I want to know about the programs")
        assert not detector.needs_language_clarification("I want to know about the Executive MBA")
        assert not detector.needs_language_clarification("Ich interessiere mich fuer die Programme")
        assert not detector.needs_language_clarification("Was sind die besten Restaurants in St. Gallen?")
        assert detector.detect_language("Welche Filme laufen heute?") == "de"
        assert detector.detect_language("Was kostet emba X?") == "de"
        assert not detector.needs_language_clarification(
            "Buenas tardes, quiero saber sobre el programa EMBA"
        )

    @pytest.mark.parametrize(
        "query",
        [
            "Wo findet emba X statt?",
            "Wo findet der Unterricht statt?",
            "Wann findet emba X statt?",
            "Was kostet emba X?",
        ],
    )
    def test_short_german_questions_use_weighted_local_signals(self, query):
        detector = LanguageDetector()

        assert not detector.needs_language_clarification(query)
        assert detector.detect_language(query) == "de"

    @pytest.mark.parametrize(
        "query",
        [
            "Where does emba X take place?",
            "When does emba X start?",
            "What does emba X cost?",
            "Which locations does emba X use?",
        ],
    )
    def test_short_english_questions_use_weighted_local_signals(self, query):
        detector = LanguageDetector()

        assert not detector.needs_language_clarification(query)
        assert detector.detect_language(query) == "en"

    def test_ambiguous_tokens_do_not_contribute_local_language_weight(self):
        detector = LanguageDetector()

        assert detector._weighted_language_signal_counts("was in im") == (0, 0)
        assert detector._quick_detect_short_words("was in im") is None

    def test_standalone_language_choice_is_explicit_switch(self):
        detector = LanguageDetector()

        assert detector.detect_explicit_switch_request("English") == "en"
        assert detector.detect_explicit_switch_request("Englisch") == "en"
        assert detector.detect_explicit_switch_request("Deutsch") == "de"
        assert detector.detect_explicit_switch_request("German") == "de"


def test_mixed_language_query_asks_user_to_choose_language():
    agent = _agent_for_language_preprocessing(language="en")

    response = agent.query("Ich want to know sobre los programs")

    assert response.response == LANGUAGE_CLARIFICATION_MESSAGE["en"]
    assert response.language == "en"
    assert agent._conversation_state["user_language"] == "ambiguous"
    assert "Would you like to continue in English or German?" in response.response
    assert not response.response.startswith("Hello.")
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_mixed_language_query_in_german_app_still_uses_english_clarification():
    agent = _agent_for_language_preprocessing(language="de")

    response = agent.query("Ich want to know sobre los programs")

    assert response.response == LANGUAGE_CLARIFICATION_MESSAGE["en"]
    assert response.language == "en"
    assert agent._conversation_state["user_language"] == "ambiguous"
    assert "Would you like to continue in English or German?" in response.response
    assert not response.response.startswith("Guten Tag")
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_mid_conversation_language_clarification_does_not_greet_again():
    agent = _agent_for_language_preprocessing(language="en")
    agent._conversation_history = [
        HumanMessage("How much does the EMBA cost?"),
        AIMessage("The EMBA tuition is CHF 77,500."),
    ]

    response = agent.query("Ich want to know sobre los programs")

    assert response.response == LANGUAGE_CLARIFICATION_MESSAGE["en"]
    assert response.language == "en"
    assert not response.response.startswith("Hello.")
    assert agent._conversation_state["user_language"] == "ambiguous"
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_unsupported_language_query_uses_supported_language_fallback():
    agent = _agent_for_language_preprocessing(language="en")

    response = agent.query("Buenas tardes, quiero saber sobre el programa EMBA")

    assert response.response == LANGUAGE_FALLBACK_MESSAGE["en"]
    assert response.language == "en"
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_unsupported_non_latin_query_uses_supported_language_fallback():
    agent = _agent_for_language_preprocessing(language="en")

    response = agent.query(
        "\u0414\u043e\u0431\u0440\u044b\u0439 \u0434\u0435\u043d\u044c, "
        "\u0445\u043e\u0447\u0443 \u0443\u0437\u043d\u0430\u0442\u044c "
        "\u0431\u043e\u043b\u044c\u0448\u0435 \u043e EMBA"
    )

    assert response.response == LANGUAGE_FALLBACK_MESSAGE["en"]
    assert response.language == "en"
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_short_german_embax_query_reaches_lead_agent(monkeypatch):
    agent = _agent_for_language_preprocessing(language="en")
    lead_calls = []

    def fake_query_lead(preprocessed_query, on_delta=None):
        lead_calls.append((preprocessed_query, on_delta))
        return LeadAgentQueryResponse(
            response="Das Programm findet in Zürich und St. Gallen statt.",
            language=agent._stored_language,
            processed_query=preprocessed_query,
        )

    monkeypatch.setattr(agent, "_query_lead", fake_query_lead)

    response = agent.query("Wo findet emba X statt?")

    assert lead_calls == [("Wo findet emba X statt?", None)]
    assert agent._stored_language == "de"
    assert agent._conversation_state["user_language"] == "de"
    assert response.language == "de"
    assert response.response not in LANGUAGE_CLARIFICATION_MESSAGE.values()
    assert response.response not in LANGUAGE_FALLBACK_MESSAGE.values()


def test_lead_prompt_obeys_preprocessed_language_routing():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Language selection and clarification are handled before this agent is called." in prompt
    assert "Treat the explicit response-language instruction as authoritative" in prompt
    assert "proper name of a programme" not in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
