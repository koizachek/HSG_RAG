from src.const.agent_response_constants import NOT_VALID_QUERY_MESSAGE
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.input_handler import InputHandler
from src.rag.scope_guardian import ScopeGuardian


class _EnglishLanguageDetector:
    @staticmethod
    def detect_explicit_switch_request(message):
        return None

    @staticmethod
    def is_language_neutral_program_reference(message):
        return False

    @staticmethod
    def detect_language(message):
        return "en"


def _agent_for_input_handling(language: str = "en") -> ExecutiveAgentChain:
    agent = object.__new__(ExecutiveAgentChain)
    agent._stored_language = language
    agent._conversation_history = []
    agent._pending_continuation = None
    agent._input_handler = InputHandler()
    agent._scope_guardian = ScopeGuardian()
    agent._language_detector = _EnglishLanguageDetector()
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


def test_repeated_invalid_inputs_suggest_admissions_contact():
    agent = _agent_for_input_handling()

    first_response = agent.query("aklwjkenmjk")
    second_response = agent.query("oekeolw 12112")

    assert first_response.response == NOT_VALID_QUERY_MESSAGE["en"]
    assert "admissions team" in second_response.response.lower()
    assert "emba@unisg.ch" in second_response.response
    assert agent._invalid_input_count == 2


def test_valid_input_resets_invalid_input_count():
    agent = _agent_for_input_handling()
    agent._invalid_input_count = 1

    response = agent.query("Can you recommend restaurants?")

    assert response.response
    assert agent._invalid_input_count == 0


def test_invalid_input_count_resets_with_conversation_state():
    agent = _agent_for_input_handling()
    agent._invalid_input_count = 2
    agent._scope_violation_counts = {"off_topic": 1}
    agent._aggressive_violation_count = 1

    agent.reset_conversation_state()

    assert agent._invalid_input_count == 0
    assert agent._scope_violation_counts == {}
    assert agent._aggressive_violation_count == 0
