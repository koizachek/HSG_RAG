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
    ],
)
def test_process_input_accepts_normal_inputs(message):
    processed, is_valid = InputHandler.process_input(message, [])

    assert is_valid
    assert processed == message.strip()


def test_process_input_keeps_numeric_follow_up_handling():
    processed, is_valid = InputHandler.process_input("5", [])

    assert is_valid
    assert "5 years" in processed.lower()
