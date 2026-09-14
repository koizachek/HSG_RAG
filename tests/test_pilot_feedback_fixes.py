"""
Regression tests for the defects found in the August 2026 pilot
(docs/pilot_august_2026_findings.md). Every case below is an exact user
message from a pilot transcript or the deterministic mechanism behind it.
"""
import pytest

from src.const.agent_response_constants import LANGUAGE_FALLBACK_MESSAGE
from src.const.data_consent_constants import BOOKING_WIDGET_HTML
from src.rag.language_detection import LanguageDetector
from src.rag.prompts import PromptConfigurator
from src.rag.scope_guardian import ScopeGuardian
from src.rag.utilclasses import LeadAgentQueryResponse
from src.scraping.url_normalizer import UrlNormalizer
from tests.test_language_handling import _agent_for_language_preprocessing


# --- Fix 1: "I am ..." is not a mixed-language message -----------------------

PILOT_ENGLISH_MESSAGES_FLAGGED_AS_MIXED = [
    "i am 26 years old, work in pharma and want to get an emba from hsg",
    "How do I know if I am eligble?",
    "I am interested in the programme, but I already know that i cannot take that many days off of work. what could the programm offer me?",
    "I am a young CEO, started my company at 21, now I am 26. I know my age may be best suited for an MBA programme- or so they say.",
    "I want the IEMBA or the EMBA X. Which is better for someone that once international recognition, who wants everyone to know they are smart. I am comparing against Harvard, IMD, Oxford.",
]


@pytest.mark.parametrize("message", PILOT_ENGLISH_MESSAGES_FLAGGED_AS_MIXED)
def test_english_messages_with_i_am_are_not_mixed_language(message):
    detector = LanguageDetector()

    assert detector.needs_language_clarification(message) is False
    assert detector.detect_language(message) == "en"


def test_real_mixed_language_still_asks_for_clarification():
    detector = LanguageDetector()

    assert detector.needs_language_clarification(
        "Ich möchte wissen how much the programme costs and wann es startet"
    )


# --- Fix 2: undecidable short inputs keep the conversation language ---------

@pytest.mark.parametrize("greeting", ["guten Tag", "guten tag", "Guten Morgen", "grüezi"])
def test_german_greetings_are_detected_as_german(greeting):
    assert LanguageDetector().detect_language(greeting) == "de"


@pytest.mark.parametrize("message", ["test", "hii", "halooo", "dasd", "erds"])
def test_signal_free_inputs_are_not_confidently_unsupported(message):
    assert LanguageDetector().is_confidently_unsupported(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "Buenas tardes, quiero saber sobre el programa EMBA",
        "Добрый день, EMBA",
    ],
)
def test_real_foreign_language_is_confidently_unsupported(message):
    assert LanguageDetector().is_confidently_unsupported(message) is True


@pytest.mark.parametrize("message", ["test", "hii", "halooo", "guten Tag"])
def test_undecidable_input_keeps_language_and_reaches_the_agent(monkeypatch, message):
    agent = _agent_for_language_preprocessing(language="de")
    lead_calls = []

    def fake_query_lead(preprocessed_query, on_delta=None):
        lead_calls.append(preprocessed_query)
        return LeadAgentQueryResponse(
            response="Wie kann ich helfen?",
            language=agent._stored_language,
            processed_query=preprocessed_query,
        )

    monkeypatch.setattr(agent, "_query_lead", fake_query_lead)

    response = agent.query(message)

    assert lead_calls == [message]
    assert response.language == "de"
    assert response.response not in LANGUAGE_FALLBACK_MESSAGE.values()


def test_spanish_input_still_gets_the_fallback_message():
    agent = _agent_for_language_preprocessing(language="en")

    response = agent.query("Buenas tardes, quiero saber sobre el programa EMBA")

    assert response.response == LANGUAGE_FALLBACK_MESSAGE["en"]


# --- Fix 3: programme financing questions are on topic ----------------------

@pytest.mark.parametrize(
    "message",
    [
        "tell me more about the loan",
        "send me a link to the website where they talk about loan",
        "I just want access to the general information page/ brochure about financing options",
        "ich habe ein budget von 40'000",
        "gibt es stipendien möglichkeiten?",
        "how many ECTS credits does the EMBA have?",
    ],
)
def test_programme_financing_questions_are_on_topic(message):
    assert ScopeGuardian.check_scope(message) == "on_topic"


@pytest.mark.parametrize(
    "message",
    ["Can you create a payment plan?", "should I take a mortgage to pay for this", "Erstellen Sie mir einen Sparplan"],
)
def test_personal_financial_planning_is_still_redirected(message):
    assert ScopeGuardian.check_scope(message) == "financial_planning"


def test_frustrated_comparison_is_not_aggressive():
    assert ScopeGuardian.check_scope("i wont book if i dont know the fee, worst then imd!!") == "on_topic"


def test_insults_are_still_aggressive():
    assert ScopeGuardian.check_scope("This chatbot is useless") == "aggressive"


# --- Fix 4: conversation length ---------------------------------------------

def test_conversation_allows_at_least_twenty_user_questions():
    from src.config import config

    assert config.convstate.MAX_CONVERSATION_TURNS >= 40


# --- Fix 5: booking widget shows which advisor is selected ------------------

@pytest.mark.parametrize("lang", ["en", "de"])
def test_booking_widget_buttons_mark_the_selected_advisor(lang):
    html = BOOKING_WIDGET_HTML[lang]

    assert html.count("<button") == 3
    # every button resets its siblings, marks itself, and reveals the frame
    assert html.count("this.parentNode.children") == 3
    assert html.count("this.style.background='white'") == 3
    assert html.count("scrollIntoView") == 3
    assert f"booking-frame-{lang}" in html


# --- Fix 6: official links in the lead prompt --------------------------------

@pytest.mark.parametrize("lang", ["en", "de"])
def test_lead_prompt_lists_official_links_only(lang):
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", lang)

    assert "OFFICIAL LINKS" in prompt
    assert "https://embax.ch/" in prompt
    assert "https://op.unisg.ch/" in prompt
    assert "programm/iemba" in prompt
    for dead_url in ("iemba.unisg.ch", "emba-x.ch"):
        assert prompt.count(dead_url) == 1, "dead URL may only appear in the prohibition"


# --- Fix 7: identity, estimates, fit questions, closed deadlines -------------

def test_lead_prompt_contains_pilot_conduct_rules():
    prompt = PromptConfigurator.get_configured_agent_prompt("lead", "en")

    assert "Do not name model providers" in prompt
    assert "Experience-based estimates presented as facts" in prompt
    assert "ask two or three short clarifying questions first" in prompt
    assert 'Do not answer "can I still apply?" with a flat "no"' in prompt
    assert "Never turn a price question into a refusal" in prompt
    assert "sur dossier" in prompt


# --- Fix 8: the bot's own pages are not indexed ------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://emba.unisg.ch/chatbot-test-consent",
        "https://emba.unisg.ch/en/chatbot-test-consent",
        "https://emba.unisg.ch/chatbot-test",
    ],
)
def test_chatbot_pages_are_blacklisted(url):
    assert UrlNormalizer.is_url_blacklisted(url) is True


def test_programme_pages_are_not_blacklisted():
    assert UrlNormalizer.is_url_blacklisted("https://emba.unisg.ch/bewerbung/process") is False


# --- Fix 9: the weekly report counts language refusals -----------------------

def test_usage_report_counts_language_outcomes(tmp_path):
    import json
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import usage_report
    from tests.test_usage_report import _event, SESSION_A

    logs = tmp_path / "logs"
    (logs / "usage").mkdir(parents=True)
    (logs / "consent").mkdir()
    events = [
        _event(SESSION_A, 1, outcome="language_clarification",
               timing={"total_s": 0.001, "preprocess_s": 0.001, "first_token_s": None}),
        _event(SESSION_A, 2, outcome="language_fallback",
               timing={"total_s": 0.001, "preprocess_s": 0.001, "first_token_s": None}),
        _event(SESSION_A, 3),
    ]
    (logs / "usage" / f"usage_{SESSION_A}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )

    metrics = usage_report.collect_metrics(str(logs), window_days=7)
    markdown = usage_report.render_markdown(metrics)

    assert metrics["risks"]["language_clarification_turns"] == 1
    assert metrics["risks"]["language_fallback_turns"] == 1
    assert "Language clarification turns" in markdown
    assert "Language fallback turns" in markdown
