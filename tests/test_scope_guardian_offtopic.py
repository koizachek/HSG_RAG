import pytest

from src.rag.scope_guardian import ScopeGuardian


@pytest.mark.parametrize(
    "message",
    [
        "Can you recommend a restaurant?",
        "Can you recommend restaurants?",
        "Welche Restaurants können Sie empfehlen?",
        "What is the weather today?",
        "Who won the sports match?",
    ],
)
def test_off_topic_queries_are_detected(message):
    assert ScopeGuardian.check_scope(message) == "off_topic"


def test_german_off_topic_redirect_acknowledges_restaurant_subject():
    message = ScopeGuardian.get_redirect_message("off_topic", "de")

    assert "Restaurants" in message
    assert "kann ich leider nicht beraten" in message
    assert "HSG Executive MBA" in message


@pytest.mark.parametrize(
    "message",
    [
        "What are the admission requirements for EMBA?",
        "How much does the programme cost?",
        "I work in healthcare and want to strengthen my leadership skills.",
    ],
)
def test_on_topic_queries_remain_allowed(message):
    assert ScopeGuardian.check_scope(message) == "on_topic"


def test_financial_planning_queries_keep_their_classification():
    assert ScopeGuardian.check_scope("Can you create a payment plan?") == "financial_planning"


def test_aggressive_queries_keep_their_classification():
    assert ScopeGuardian.check_scope("This chatbot is useless") == "aggressive"
