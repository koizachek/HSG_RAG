from src.const.agent_response_constants import NOT_VALID_QUERY_MESSAGE
from src.rag.agent_chain import ExecutiveAgentChain


def _agent_for_invalid_input(language: str = "en") -> ExecutiveAgentChain:
    agent = object.__new__(ExecutiveAgentChain)
    agent._stored_language = language
    agent._conversation_history = []
    agent._fallback_counters = {
        "invalid_input": 0,
        "aggressive": 0,
        "scope_violations": {},
    }
    return agent


def test_repeated_invalid_inputs_suggest_admissions_contact():
    agent = _agent_for_invalid_input("en")

    first_response = agent.query("aklwjkenmjk")
    second_response = agent.query("oekeolw 12112")

    assert first_response.response == NOT_VALID_QUERY_MESSAGE["en"]
    assert "admissions team" in second_response.response.lower()
    assert "emba@unisg.ch" in second_response.response
    assert agent._fallback_counters["invalid_input"] == 2


def test_invalid_input_count_resets_with_conversation_state():
    agent = _agent_for_invalid_input("en")
    agent._fallback_counters = {
        "invalid_input": 2,
        "aggressive": 1,
        "scope_violations": {"off_topic": 1},
    }
    agent._pending_continuation = None
    agent._programme_overview_detail_level = 0
    agent._programme_overview_profile_context = False
    agent._conversation_state = {
        "session_id": "session-1",
        "user_id": "session-1",
        "user_language": "en",
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

    agent.reset_conversation_state()

    assert agent._fallback_counters == {
        "invalid_input": 0,
        "aggressive": 0,
        "scope_violations": {},
    }
