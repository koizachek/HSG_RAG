from gradio import ChatMessage

""" Constants for Gradio app """

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
        "Möchten Sie unser Gespräch auf Englisch fortführen?"
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
                "Cyra von Müller",
                "Book Appointment"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
                "Kristin Fuchs",
                "Book Appointment"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/teyuna-giger-unisg",
                "Teyuna Giger",
                "Book Appointment"
            ),
        ),
    ],
    "de": [
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
                "Cyra von Müller",
                "Termin buchen"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
                "Kristin Fuchs",
                "Termin buchen"
            ),
        ),
        ChatMessage(
            role="assistant",
            content=create_appt_button(
                "https://calendly.com/teyuna-giger-unisg",
                "Teyuna Giger",
                "Termin buchen"
            ),
        ),
    ],
}
