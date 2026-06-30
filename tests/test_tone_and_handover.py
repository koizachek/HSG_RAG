import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("REDIS_CLOUD_PORT", "6379")

if "colorama" not in sys.modules:
    sys.modules["colorama"] = types.SimpleNamespace(
        Fore=types.SimpleNamespace(CYAN="", GREEN="", YELLOW="", RED="", MAGENTA=""),
        Style=types.SimpleNamespace(BRIGHT="", RESET_ALL=""),
        init=lambda *args, **kwargs: None,
    )

from src.const.agent_response_constants import (
    GREETING_MESSAGES,
    get_admissions_contact_text,
    get_booking_widget,
)
from langchain_core.messages import AIMessage
from src.rag import agent_chain as agent_chain_module
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.conversation_state import ConversationStateManager
from src.rag.prompts import PromptConfigurator
from src.rag.scope_guardian import ScopeGuardian


def test_lead_prompt_requires_professional_complete_sentences():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Professional, university-level tone" in prompt
    assert "Complete sentences" in prompt
    assert "professional British English" in prompt
    assert 'Avoid casual phrasing like "Great to meet you"' in prompt


def test_lead_prompt_keeps_booking_user_led():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Routine informational turns keep both flags `False`" in prompt
    assert "show_booking_widget=True" in prompt
    assert "the user explicitly asks to book" in prompt
    assert "Kristin Fuchs" in prompt


def test_lead_prompt_uses_stage_sensitive_programme_positioning():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Match framing to the conversation stage" in prompt
    assert "Early discovery: balanced and factual" in prompt
    assert "Expressed interest in one programme" in prompt
    assert "answer first, then add positive value framing" in prompt


def test_lead_prompt_contains_programme_specific_positive_value_framing():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "German query + general/DACH focus" in prompt
    assert "English query + international focus" in prompt
    assert "Tech / innovation / transformation focus or tech background" in prompt
    assert "positive value framing" in prompt


def test_lead_prompt_preserves_credibility_and_avoids_hype():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert 'Avoid hype words ("best", "world-class", "perfect", "guaranteed")' in prompt
    assert "retrieved content explicitly supports them" in prompt


def test_lead_prompt_uses_ordered_eligibility_fallbacks():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "assess whether EMBA HSG, IEMBA HSG, or emba X is a better fit" in prompt
    assert "only when its retrieved requirements and positioning support the fit" in prompt
    assert "If none of the three Executive MBA programmes fits" in prompt
    assert "regular HSG MBA" in prompt
    assert "clear admissions contact path" in prompt
    assert "emba@unisg.ch" in prompt


def test_lead_prompt_handles_frustration_with_acknowledgement_and_handover():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "briefly acknowledge the concern" in prompt
    assert "without defensiveness or promotional language" in prompt
    assert "clear path to discuss the concern with an advisor or admissions contact" in prompt
    assert "If the aggression continues, prioritise human handover" in prompt
    assert "exception to the no-validation rule" in prompt


def test_lead_prompt_uses_contact_path_for_soft_handover():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "For soft human handover" in prompt
    assert "emba@unisg.ch" in prompt
    assert "+41 71 224 27 02" in prompt


def test_booking_intent_detector_requires_user_initiative():
    agent = ExecutiveAgentChain.__new__(ExecutiveAgentChain)
    agent._conversation_history = []
    agent._state_manager = ConversationStateManager(agent)

    assert not agent._is_explicit_booking_intent("What does the EMBA cost?")
    assert not agent._is_explicit_booking_intent("Which programme fits my profile better?")
    assert agent._is_explicit_booking_intent("I would like to book a consultation.")
    assert agent._is_explicit_booking_intent("Kann ich einen Termin vereinbaren?")
    assert not agent._is_explicit_booking_intent("Ich möchte keinen Termin buchen.")


def test_booking_intent_detector_accepts_previous_soft_offer():
    agent = ExecutiveAgentChain.__new__(ExecutiveAgentChain)
    agent._conversation_history = [
        AIMessage("If you would like to discuss this personally, I can also help you with appointment booking.")
    ]
    agent._state_manager = ConversationStateManager(agent)

    assert agent._is_explicit_booking_intent("Yes please")
    assert not agent._is_explicit_booking_intent("Ich habe 5 Jahre Berufserfahrung.")

    agent_without_offer = ExecutiveAgentChain.__new__(ExecutiveAgentChain)
    agent_without_offer._conversation_history = []
    agent_without_offer._state_manager = ConversationStateManager(agent_without_offer)

    assert not agent_without_offer._is_explicit_booking_intent("Yes please")


def test_booking_preference_follow_up_is_detected_in_active_flow():
    agent = ExecutiveAgentChain.__new__(ExecutiveAgentChain)
    agent._conversation_history = [
        AIMessage(
            "Vielen Dank für die Rückmeldung. Ich kann Ihnen nun passende Terminoptionen "
            "anzeigen. Eine kurze letzte Frage, damit die Slots besser passen: "
            "Haben Sie eine Tagespräferenz und bevorzugen Sie vormittags oder nachmittags?"
        )
    ]
    agent._conversation_state = {"handover_requested": True}

    assert agent._previous_response_requested_booking_preferences()
    assert agent._is_booking_preference_follow_up("online")
    assert agent._is_booking_preference_follow_up("vormittags, anfang der woche")
    assert not agent._is_booking_preference_follow_up("Was kostet das Programm?")


def test_response_commit_detector_requires_show_now_not_soft_offer():
    agent = ExecutiveAgentChain.__new__(ExecutiveAgentChain)

    assert agent._response_commits_to_showing_booking_widget(
        "Ich kann Ihnen nun passende Terminoptionen anzeigen. Unten werden Ihnen die verfügbaren Slots eingeblendet."
    )
    assert not agent._response_commits_to_showing_booking_widget(
        "Wenn Sie möchten, kann ich Ihnen später auch bei der Terminbuchung helfen."
    )
    assert not agent._response_commits_to_showing_booking_widget(
        "Bitte noch kurz: Bevorzugen Sie vormittags oder nachmittags?"
    )
def test_soft_booking_offer_does_not_mark_handover_state(monkeypatch):
    monkeypatch.setattr(agent_chain_module.config.convstate, "TRACK_USER_PROFILE", True)

    agent = ExecutiveAgentChain.__new__(ExecutiveAgentChain)
    agent._conversation_state = {
        "session_id": "test-session",
        "user_id": "test-session",
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
    agent._conversation_history = []
    agent._state_manager = ConversationStateManager(agent)

    agent._state_manager.update(
        "Was kostet das EMBA HSG?",
        "If you would like to discuss this personally, I can also help you with appointment booking.",
    )

    assert agent._conversation_state["handover_requested"] is None


def test_iemba_booking_widget_shows_contact_details_and_slots():
    widget = get_booking_widget(language="en", programs=["iemba"])

    assert "Kristin Fuchs (IEMBA)" in widget
    assert "kristin.fuchs@unisg.ch" in widget
    assert "+41 71 224 75 46" in widget
    assert "available appointment slots and contact details" in widget
    assert "calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation" in widget
    assert "Cyra von Müller (EMBA)" not in widget


def test_scope_guardian_escalation_uses_real_contact_details():
    message = ScopeGuardian.get_escalation_message("escalate_off_topic", "en")

    assert "[admissions contact info]" not in message
    assert get_admissions_contact_text("en") in message
    assert "emba@unisg.ch" in message
    assert "+41 71 224 27 02" in message


def test_escalation_language_fallback_preserves_escalation_type():
    message = ScopeGuardian.get_escalation_message("escalate_aggressive", "fr")

    assert "language is aggressive" in message
    assert "questions outside programme information" not in message


def test_english_greetings_use_formal_opening():
    for greeting in GREETING_MESSAGES["en"]:
        assert "Hello and welcome." in greeting
        assert "!" not in greeting
