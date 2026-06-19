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
