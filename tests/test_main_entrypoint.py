import sys

import main as app_entrypoint


def test_main_runs_requested_chat_application_language(monkeypatch):
    calls = []

    monkeypatch.setattr(sys, "argv", ["main.py", "--app", "de"])
    monkeypatch.setattr(
        app_entrypoint,
        "run_application",
        lambda lang="en": calls.append(("app", lang)),
    )

    app_entrypoint.main()

    assert calls == [("app", "de")]


def test_main_defaults_to_english_chat_application(monkeypatch):
    calls = []

    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setattr(
        app_entrypoint,
        "run_application",
        lambda lang="en": calls.append(("app", lang)),
    )

    app_entrypoint.main()

    assert calls == [("app", "en")]
