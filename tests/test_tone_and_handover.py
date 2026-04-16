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
from src.rag.prompts import PromptConfigurator
from src.rag.scope_guardian import ScopeGuardian


def test_lead_prompt_requires_professional_complete_sentences():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Maintain a professional, university-level tone" in prompt
    assert "Use complete sentences." in prompt
    assert "professional British English" in prompt
    assert 'Avoid informal phrasing such as "Great to meet you"' in prompt


def test_lead_prompt_requires_clear_iemba_embax_handover():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", language="en")

    assert "Primary recommendation: **IEMBA HSG**" in prompt
    assert "Alternative to consider: **emba X**" in prompt
    assert "After such a comparison, proactively offer handover" in prompt
    assert "**Kristin Fuchs**" in prompt
    assert "relevant contact details and appointment options are shown below" in prompt


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


def test_english_greetings_use_formal_opening():
    for greeting in GREETING_MESSAGES["en"]:
        assert "Hello and welcome." in greeting
        assert "!" not in greeting
