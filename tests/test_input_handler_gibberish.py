import pytest

from src.rag.input_handler import InputHandler


@pytest.mark.parametrize(
    "message",
    [
        "asdfkjhasdf 12345 !!!????",
        "!!!????",
        "qwer zxcv asdf",
        "bcdfghjklmnp",
        "12345 !!!????",
        "sdfghjkllkjh",
        "aklwjkenmjk",
        "oekeolw 12112",
        "2o2oksmd,s",
        "olll.skldaal",
        "lsopwoelkfl",
        "1qokimjdk",
    ],
)
def test_process_input_rejects_probable_gibberish(message):
    processed, is_valid = InputHandler.process_input(message, [])

    assert not is_valid
    assert processed == message.strip()


@pytest.mark.parametrize(
    "message",
    [
        "What are the admission requirements for the EMBA?",
        "Can I book a consultation?",
        "IEMBA",
        "emba X",
        "yes",
        "Nein",
        "St. Gallen",
        "CV",
        "EMBA 2026",
        "Zurich 8000",
        "leadership 2026",
        "Was sind die nächsten Schritte im Bewerbungsprozess?",
        # Regression: real queries the gibberish heuristic wrongly rejected.
        # German compound words contain long consonant runs ("deutschsprachige");
        # long English sentences false-positived once their words were concatenated.
        "Wie lange dauert der deutschsprachige EMBA HSG?",
        "Give me a short overview of all three executive MBA programmes.",
        "Welche Weiterbildungsmöglichkeiten bietet die Universität?",
        "Ich interessiere mich für ein MBA mit Schwerpunkt nachhaltige Unternehmensführung.\nberufsbegleitend.",
        "Ich habe gerade meinen Bachelor abgeschlossen und 2 Jahre Berufserfahrung. Kann ich mich für den Executive MBA bewerben?",
    ],
)
def test_process_input_accepts_normal_inputs(message):
    processed, is_valid = InputHandler.process_input(message, [])

    assert is_valid
    assert processed == message.strip()


@pytest.mark.parametrize(
    "message",
    [
        "\u0414\u043e\u0431\u0440\u044b\u0439 \u0434\u0435\u043d\u044c, \u0445\u043e\u0447\u0443 \u0443\u0437\u043d\u0430\u0442\u044c \u0431\u043e\u043b\u044c\u0448\u0435 \u043e \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0435 EMBA",
        "\u0645\u0633\u0627\u0621 \u0627\u0644\u062e\u064a\u0631\u060c \u0623\u0631\u064a\u062f \u0645\u0639\u0631\u0641\u0629 \u0627\u0644\u0645\u0632\u064a\u062f \u0639\u0646 EMBA",
    ],
)
def test_process_input_accepts_unsupported_languages_for_language_fallback(message):
    processed, is_valid = InputHandler.process_input(message, [])

    assert is_valid
    assert processed == message.strip()


@pytest.mark.parametrize(
    "message",
    [
        "How much does the IEMBA cost in CHF?",
        "Does emba X require 10 years of experience?",
        "I have 12 years of experience and 4 years of leadership.",
        "Can you compare EMBA, IEMBA, and emba X?",
        "When is the next application deadline?",
        "I live in Zurich. Is the programme hybrid or in person?",
        "Can I speak with admissions?",
        "Do I need GMAT or TOEFL?",
        "What documents should I prepare: CV, diploma, references?",
        "Is the programme compatible with a full-time job?",
        "Wie hoch sind die Studiengebühren?",
        "Welche Unterlagen brauche ich für die Bewerbung?",
        "Ich habe 8 Jahre Berufserfahrung und 3 Jahre Führungserfahrung.",
        "Kann ich das Programm berufsbegleitend absolvieren?",
        "Gibt es Module im Ausland?",
        "Wann ist die nächste Bewerbungsfrist?",
        "Ich wohne in Zürich. Gibt es Präsenztermine?",
        "Brauche ich GMAT oder TOEFL?",
        "Können Sie EMBA, IEMBA und emba X vergleichen?",
        "Ich möchte mit der Studienberatung sprechen.",
        "Guten Tag,\nich interessiere mich für das EMBA HSG.",
        "Hello - I am comparing EMBA vs. IEMBA.",
        "Bewerbungsfrist?",
        "Studiengebühren",
        "duration",
        "GMAT/TOEFL",
        "CV?",
        "IEMBA 2026?",
        "St.Gallen?",
        "Zurich/St.Gallen",
        "EMBA, IEMBA oder emba X?",
        "Deutsch or English?",
        "I prefer Deutsch.",
        "Wie bitte?",
        "More about fees?",
        "Kosten + Termine?",
        "MBA in St. Gallen",
        "I have 9 years, no management yet.",
        "Ich habe 9 Jahre, aber keine Führung.",
    ],
)
def test_process_input_accepts_realistic_user_queries(message):
    processed, is_valid = InputHandler.process_input(message, [])

    assert is_valid
    assert processed == message.strip()


def test_process_input_keeps_numeric_follow_up_handling():
    processed, is_valid = InputHandler.process_input("5", [])

    assert is_valid
    assert "5 years" in processed.lower()
