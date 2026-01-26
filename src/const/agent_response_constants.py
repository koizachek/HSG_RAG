from gradio import ChatMessage

""" Constants for Gradio app """

GREETING_MESSAGES = {
        "en": [
            "Hello and welcome! I’m your Executive Education Advisor for the HSG Executive MBA programs (**IEMBA**, **emba X**, and **EMBA**). How can I best support your MBA planning today?",
            "Hello and welcome! I’m your Executive Education Advisor for the University of St.Gallen’s Executive MBA programs (**IEMBA**, **emba X**, **EMBA**). How can I support your MBA planning today?",
            "Hello and welcome! I’m your Executive Education Advisor for the HSG Executive MBA programs (**EMBA**, **IEMBA**, **emba X**). How can I help you with your EMBA journey today?",
            "Hello and welcome! I’m your Executive Education Advisor for the University of St.Gallen’s EMBA programs, here to help you navigate our **EMBA**, **IEMBA**, and **emba X** options.",
            "Hello and welcome. I’m your Executive Education Advisor for the University of St.Gallen’s Executive MBA programs, here to help you assess fit and navigate the **EMBA**, **IEMBA**, and **emba X** options.",
        ],
        "de": [
            "Guten Tag! Ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme und unterstütze Sie gerne bei Fragen zu **EMBA**, **IEMBA** und **emba X**.",
            "Guten Tag, ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme (**EMBA**, **IEMBA**, **emba X**). Ich unterstütze Sie bei Programmwahl, Ablauf und Zulassungsfragen.",
            "Guten Tag und herzlich willkommen! Ich bin Ihr Executive Education Advisor für die HSG Executive MBA Programme und unterstütze Sie gern bei Fragen zu **EMBA**, **IEMBA** und **emba X**.",
            "Guten Tag, ich bin Ihr Executive-Education-Berater für die HSG Executive MBA-Programme (**EMBA**, **IEMBA**, **emba X**) und unterstütze Sie gerne bei Programmwahl und Zulassungsfragen.",
            "Guten Tag! Ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme (**EMBA**, **IEMBA**, **emba X**) und unterstütze Sie gerne bei Programmwahl und Zulassungsfragen.",
        ]
}

QUERY_EXCEPTION_MESSAGE = {
    "en": "I'm sorry, I cannot provide a helpful response right now. Please contact tech support or try again later.",
    "de": "Es tut mir leid, ich kann im Moment keine hilfreiche Antwort geben. Bitte wenden Sie sich an den technischen Support oder versuchen Sie es später erneut.",
}

NOT_VALID_QUERY_MESSAGE = {
    "en": "I didn't quite understand that. Could you please rephrase your question?",
    "de": "Das habe ich nicht ganz verstanden. Könnten Sie Ihre Frage bitte anders formulieren?",
}

CONFIDENCE_FALLBACK_MESSAGE = {
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

LANGUAGE_FALLBACK_MESSAGE = {
    "en": (
        "I am sorry, I can only reply in English or German. "
        "Would you like to continue our conversation in English?"
    ),
    "de": (
        "Es tut mir leid, ich kann nur auf Englisch oder Deutsch antworten. "
        "Möchten Sie unser Gespräch auf Deutsch fortführen?"
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


def create_appt_button(url, title, lang_text):
    return (
        f'<a href="{url}" class="appointment-btn" '
        f'style="display: block; background-color: #f3f4f6; border: 1px solid #d1d5db; '
        f'padding: 8px 16px; border-radius: 6px; cursor: pointer; '
        f'color: #374151; font-weight: 600; width: 100%; text-align: left; '
        f'margin-top: 5px; text-decoration: none;">'
        f'📅 {lang_text}: {title}'
        f'</a>'
    )


APPOINTMENT_LINKS = {
    "en": [
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
                "Cyra von Müller (EMBA HSG)",
                "Book Appointment"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
                "Kristin Fuchs (IEMBA)",
                "Book Appointment"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/teyuna-giger-unisg",
                "Teyuna Giger (emba X)",
                "Book Appointment"
            ),
        ),
    ],
    "de": [
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
                "Cyra von Müller (EMBA HSG)",
                "Termin buchen"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
                "Kristin Fuchs (IEMBA)",
                "Termin buchen"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/teyuna-giger-unisg",
                "Teyuna Giger (emba X)",
                "Termin buchen"
            ),
        ),
    ],
}
