import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag import agent_chain as agent_chain_module
from src.rag.agent_chain import ExecutiveAgentChain
from src.rag.programme_facts import ProgrammeFacts
from src.rag.utilclasses import StructuredAgentResponse


class DummyWeaviateService:
    def query(self, *args, **kwargs):
        class _DummyResponse:
            objects = []

        return _DummyResponse(), None


class FakeLanguageDetector:
    def detect_explicit_switch_request(self, query: str) -> str | None:
        return None

    def is_language_neutral_program_reference(self, query: str) -> bool:
        return query.strip().casefold() in {
            "emba",
            "emba hsg",
            "iemba",
            "iemba hsg",
            "emba x",
            "embax",
        }

    def detect_language(self, query: str) -> str:
        query_lower = query.lower()
        if any(token in query_lower for token in ("was", "kostet", "studiengebühr", "programm")):
            return "de"
        return "en"


class FakeLeadAgent:
    name = "lead_agent"

    def invoke(self, payload, config=None, context=None):
        messages = payload["messages"]
        human_messages = [msg for msg in messages if getattr(msg, "type", None) == "human"]
        system_messages = [msg for msg in messages if getattr(msg, "type", None) == "system"]
        query = human_messages[-1].content if human_messages else ""
        query_lower = query.lower()
        response_language = "de" if any(
            "respond in german" in getattr(msg, "content", "").lower() for msg in system_messages
        ) else "en"

        if query_lower == "ich brauche eine beratung für emba hsg":
            response = StructuredAgentResponse(
                response=(
                    "Für eine individuelle Beratung zum **EMBA HSG** kann ich Ihnen gerne einen Termin "
                    "mit unserer Studienberaterin Cyra von Müller vorschlagen.\n"
                    "Bitte noch kurz:\n"
                    "• Bevorzugen Sie ein **Online-Gespräch** oder ein Gespräch **vor Ort in St.Gallen**?\n"
                    "• Haben Sie zeitliche Präferenzen (z.B. eher vormittags / nachmittags)?\n\n"
                    "Sobald ich das weiss, kann ich Ihnen geeignete Terminoptionen für ein persönliches "
                    "Beratungsgespräch anzeigen."
                ),
                appointment_requested=True,
                show_booking_widget=False,
                relevant_programs=["emba"],
            )
        elif query_lower == "online":
            response = StructuredAgentResponse(
                response=(
                    "Vielen Dank für die Rückmeldung.\n"
                    "Ich kann Ihnen nun passende Terminoptionen für ein **Online-Beratungsgespräch** "
                    "zum **EMBA HSG** mit Cyra von Müller anzeigen.\n"
                    "Eine kurze letzte Frage, damit die Slots besser passen:\n"
                    "• Haben Sie eine Tagespräferenz (z.B. eher Anfang der Woche / Ende der Woche)?\n"
                    "• Bevorzugen Sie vormittags oder nachmittags?\n\n"
                    "Sobald ich dies weiss, kann ich Ihnen die konkreten verfügbaren Online-Termine zeigen."
                ),
                appointment_requested=True,
                show_booking_widget=False,
                relevant_programs=["emba"],
            )
        elif query_lower == "vormittags, anfang der woche":
            response = StructuredAgentResponse(
                response=(
                    "Perfekt, danke für die Präzisierung.\n"
                    "Ich kann Ihnen nun **Online-Terminoptionen am Wochenanfang, vormittags,** "
                    "für eine **EMBA HSG** Beratung mit Cyra von Müller anzeigen. "
                    "Unten werden Ihnen die verfügbaren Slots sowie die Kontaktdaten eingeblendet, "
                    "aus denen Sie einen passenden Termin auswählen können."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=["emba"],
            )
        elif any(term in query_lower for term in ("termin", "appointment", "consultation", "beratungstermin")):
            response = StructuredAgentResponse(
                response=(
                    "Gerne. Ich kann Ihnen passende Terminoptionen für das **EMBA HSG** anzeigen."
                    if response_language == "de"
                    else
                    "Certainly. I can show you suitable appointment options for the **EMBA HSG**."
                ),
                appointment_requested=True,
                show_booking_widget=True,
                relevant_programs=["emba"],
            )
        elif "welches programm passt" in query_lower or "which programme fits" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Auf Basis Ihrer Angaben wirkt das **IEMBA HSG** naheliegend. "
                    "Wenn Sie später ein persönliches Gespräch wünschen, kann ich Ihnen auch "
                    "bei der Terminbuchung helfen."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif query_lower.strip() in {"emba", "emba hsg"}:
            response = StructuredAgentResponse(
                response=(
                    "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**. "
                    "In den Studiengebühren enthalten sind Kursunterlagen sowie die meisten "
                    "Mahlzeiten und Erfrischungen vor Ort. Unterkunft und Reisen sind nicht enthalten."
                    if response_language == "de"
                    else
                    "The tuition for the **EMBA HSG** is **CHF 77,500**. "
                    "Included are course materials and most on-site meals and refreshments. "
                    "Accommodation and travel are not included."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif query_lower.strip() in {"iemba", "iemba hsg"}:
            response = StructuredAgentResponse(
                response=(
                    "Die Studiengebühr für den **IEMBA HSG** beträgt **CHF 85,000**. "
                    "In den Studiengebühren enthalten sind Kursunterlagen sowie die meisten "
                    "Mahlzeiten und Erfrischungen vor Ort. Unterkunft und Reisen sind nicht enthalten."
                    if response_language == "de"
                    else
                    "The tuition for the **IEMBA HSG** is **CHF 85,000**. "
                    "Included are course materials and most on-site meals and refreshments. "
                    "Accommodation and travel are not included."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif query_lower.strip() in {"emba x", "embax"}:
            response = StructuredAgentResponse(
                response=(
                    "Die Studiengebühr für **emba X** beträgt **CHF 110,000**. "
                    "Unterkunft und Reisen sind nicht enthalten."
                    if response_language == "de"
                    else
                    "The tuition for **emba X** is **CHF 110,000**. "
                    "Accommodation and travel are not included."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif "was kostet der emba" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Meinen Sie den deutschsprachigen **EMBA HSG**, den **International EMBA (IEMBA)** "
                    "oder das **emba X** Programm?"
                ),
                appointment_requested=False,
                relevant_programs=[],
            )
        elif "emba hsg" in query_lower and "iemba" not in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**. "
                    "In den Studiengebühren enthalten sind Kursunterlagen sowie die meisten "
                    "Mahlzeiten und Erfrischungen vor Ort. Unterkunft und Reisen sind nicht enthalten."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif "iemba" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "The tuition for the **IEMBA HSG** is **CHF 85,000**. "
                    "Included are course materials and most on-site meals and refreshments. "
                    "Accommodation and travel are not included."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif "emba x" in query_lower or "embax" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "The tuition for **emba X** is **CHF 110,000**. "
                    "Accommodation and travel are not included."
                ),
                appointment_requested=False,
                show_booking_widget=False,
                relevant_programs=[],
            )
        elif "how much does the emba cost" in query_lower or "was kostet das emba programm" in query_lower:
            response = StructuredAgentResponse(
                response=(
                    "Are you interested in the **German-speaking EMBA HSG**, the "
                    "**International EMBA (IEMBA)**, or the **emba X**?"
                ),
                appointment_requested=False,
                relevant_programs=[],
            )
        else:
            response = StructuredAgentResponse(
                response="Please specify which programme you mean.",
                appointment_requested=False,
                relevant_programs=[],
            )

        return {
            "structured_response": response,
            "messages": [type("FakeMessage", (), {"text": response.response})()],
        }


class FakeProgrammeFactsProvider:
    _facts = {
        "emba": ProgrammeFacts(
            programme="emba",
            timing_points=[
                "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**. In den Studiengebühren enthalten sind Kursunterlagen sowie die meisten Mahlzeiten und Erfrischungen vor Ort. Unterkunft und Reisen sind nicht enthalten.",
            ],
            fit_points=[
                "Hochschulabschluss, Berufserfahrung und Führungserfahrung werden im Zulassungsprozess geprüft.",
            ],
        ),
        "iemba": ProgrammeFacts(
            programme="iemba",
            timing_points=[
                "The tuition for the **IEMBA HSG** is **CHF 85,000**. Included are course materials and most on-site meals and refreshments. Accommodation and travel are not included.",
            ],
            fit_points=[
                "Degree, professional experience, leadership experience and English readiness are checked in admissions.",
            ],
        ),
        "emba_x": ProgrammeFacts(
            programme="emba_x",
            timing_points=[
                "The tuition for **emba X** is **CHF 110,000**. Accommodation and travel are not included.",
            ],
            fit_points=[
                "Degree, professional experience, leadership experience and English readiness are checked in admissions.",
            ],
        ),
    }

    def get_facts(self, programme: str, language: str) -> ProgrammeFacts:
        return self._facts.get(programme, ProgrammeFacts(programme=programme))


def _fake_init_agents(self):
    agents = {
        "lead": FakeLeadAgent(),
        "emba": FakeLeadAgent(),
        "iemba": FakeLeadAgent(),
        "embax": FakeLeadAgent(),
    }
    return agents, {"configurable": {"thread_id": 0}}


@pytest.fixture
def offline_agent(monkeypatch):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(agent_chain_module, "LanguageDetector", FakeLanguageDetector)
    monkeypatch.setattr(ExecutiveAgentChain, "_init_agents", _fake_init_agents)
    monkeypatch.setattr(agent_chain_module.config.chain, "EVALUATE_RESPONSE_QUALITY", False, raising=False)
    monkeypatch.setattr(agent_chain_module.config.chain, "ENABLE_RESPONSE_CHUNKING", False, raising=False)
    agent = ExecutiveAgentChain(language="en")
    agent._programme_facts_provider = FakeProgrammeFactsProvider()
    return agent


def test_offline_smoke_emba_pricing_in_german(offline_agent):
    response = offline_agent.query("Was kostet das EMBA HSG Programm?")

    assert response.language == "de"
    assert "Kosten" in response.response
    assert "CHF 77'500" in response.response
    assert "Unterkunft und Reisen sind nicht enthalten" not in response.response
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_offline_smoke_iemba_pricing_in_english(offline_agent):
    response = offline_agent.query("What is the tuition for the IEMBA?")

    assert response.language == "en"
    assert "Cost" in response.response
    assert "CHF 85,000" in response.response
    assert "Accommodation and travel are not included" not in response.response
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_offline_smoke_embax_pricing_with_deadlines(offline_agent):
    response = offline_agent.query("How much does emba X cost?")

    assert response.language == "en"
    assert "Cost" in response.response
    assert "CHF 99,000" not in response.response
    assert "31 August 2026" not in response.response
    assert "CHF 110,000" in response.response
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_offline_smoke_ambiguous_pricing_question_requests_clarification(offline_agent):
    response = offline_agent.query("How much does the EMBA cost?")

    assert "German-speaking EMBA HSG" in response.response
    assert "International EMBA (IEMBA)" in response.response
    assert "emba X" in response.response
    assert response.appointment_requested is False
    assert response.show_booking_widget is False
    assert response.relevant_programs == []


def test_offline_smoke_program_name_follow_up_keeps_previous_language(offline_agent):
    first_response = offline_agent.query("Was kostet der EMBA?")

    assert first_response.language == "de"
    assert "Meinen Sie" in first_response.response

    second_response = offline_agent.query("EMBA")

    assert second_response.language == "de"
    assert offline_agent._stored_language == "de"
    assert "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**." in second_response.response
    assert second_response.appointment_requested is False
    assert second_response.show_booking_widget is False
    assert second_response.relevant_programs == []


@pytest.mark.parametrize(
    ("follow_up", "expected_snippet"),
    [
        ("EMBA", "Die Studiengebühr für das **EMBA HSG** beträgt **CHF 77,500**."),
        ("IEMBA", "Die Studiengebühr für den **IEMBA HSG** beträgt **CHF 85,000**."),
        (
            "emba X",
            "Die Studiengebühr für **emba X** beträgt **CHF 110,000**.",
        ),
    ],
)
def test_offline_smoke_all_programme_names_as_second_user_reply_keep_german(
    offline_agent, follow_up, expected_snippet
):
    first_response = offline_agent.query("Was kostet der EMBA?")

    assert first_response.language == "de"
    assert "Meinen Sie" in first_response.response

    second_response = offline_agent.query(follow_up)

    assert second_response.language == "de"
    assert offline_agent._stored_language == "de"
    assert expected_snippet in second_response.response
    assert second_response.appointment_requested is False
    assert second_response.show_booking_widget is False
    assert second_response.relevant_programs == []


def test_explicit_booking_request_shows_widget(offline_agent):
    response = offline_agent.query("Ich möchte einen Termin für das EMBA HSG buchen.")

    assert response.appointment_requested is True
    assert response.show_booking_widget is True
    assert response.relevant_programs == ["emba"]


def test_basic_recommendation_does_not_show_widget(offline_agent):
    response = offline_agent.query("Welches Programm passt zu meinem Profil?")

    assert "IEMBA HSG" in response.response
    assert "Terminbuchung" in response.response
    assert response.appointment_requested is False
    assert response.show_booking_widget is False


def test_formal_assessment_appointment_request_shows_widget(offline_agent):
    response = offline_agent.query(
        "Ich möchte einen Termin für eine formale Einschätzung meines Profils buchen."
    )

    assert response.appointment_requested is True
    assert response.show_booking_widget is True


def test_booking_follow_up_preferences_keep_flow_active_until_widget_is_shown(offline_agent):
    first_response = offline_agent.query("Ich brauche eine Beratung für EMBA HSG")

    assert first_response.appointment_requested is True
    assert first_response.show_booking_widget is False
    assert first_response.relevant_programs == ["emba"]

    second_response = offline_agent.query("online")

    assert second_response.appointment_requested is True
    assert second_response.show_booking_widget is False
    assert second_response.relevant_programs == ["emba"]

    third_response = offline_agent.query("vormittags, anfang der woche")

    assert third_response.appointment_requested is True
    assert third_response.show_booking_widget is True
    assert third_response.relevant_programs == ["emba"]
