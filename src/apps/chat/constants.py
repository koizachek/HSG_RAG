from gradio import ChatMessage

""" Constants for Gradio app """

FALLBACK_MESSAGE = {
    "en": (
        "I'm sorry, but I couldn't find any information in my records that matches your request, "
        "so I can't answer it with confidence. Could you please rephrase your question?\n\n"
        "Alternatively, you can book an appointment with a student services advisor using the links below."
    ),
    "de": (
        "Es tut mir leid, aber ich konnte in meinen Unterlagen keine Informationen finden, "
        "die zu Ihrer Anfrage passen, sodass ich sie nicht mit ausreichender Sicherheit beantworten kann. "
        "Könnten Sie Ihre Frage bitte umformulieren?\n\n"
        "Alternativ können Sie über die untenstehenden Links einen Termin bei der Studienberatung buchen."
    ),
}

CONVERSATION_END_MESSAGE = {
    "en": (
        "This conversation has reached its maximum length. "
        "To make sure you receive the best possible support, "
        "please continue with a personal consultation.\n\n"
        "You can book an appointment with a student services advisor using the links below. "
        "Thank you for your understanding."
    ),
    "de": (
        "Dieses Gespräch hat die maximale Länge erreicht. "
        "Damit Sie bestmöglich unterstützt werden, bitten wir Sie, "
        "das Anliegen in einem persönlichen Beratungsgespräch fortzusetzen.\n\n"
        "Über die untenstehenden Links können Sie einen Termin mit der Studienberatung buchen. "
        "Vielen Dank für Ihr Verständnis."
    ),
}

APPOINTMENT_LINKS = {
    "en": [
        ChatMessage(
            role="assistant",
            content="https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
            metadata={
                "title": "Cyra von Müller, Head of Recruitment & Admissions – EMBA HSG Program"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
            metadata={
                "title": "Kristin Fuchs, Head of Recruitment & Admissions – International EMBA HSG Program"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/teyuna-giger-unisg",
            metadata={
                "title": "Teyuna Giger, Head of Recruitment & Admissions – EMBA ETH HSG (emba X) Program"
            },
        ),
    ],
    "de": [
        ChatMessage(
            role="assistant",
            content="https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
            metadata={
                "title": "Cyra von Müller, Leitung Rekrutierung & Zulassung – EMBA HSG Programm"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
            metadata={
                "title": "Kristin Fuchs, Leitung Rekrutierung & Zulassung – Internationales EMBA HSG Programm"
            },
        ),
        ChatMessage(
            role="assistant",
            content="https://calendly.com/teyuna-giger-unisg",
            metadata={
                "title": "Teyuna Giger, Leitung Rekrutierung & Zulassung – EMBA ETH HSG (emba X) Programm"
            },
        ),
    ],
}
