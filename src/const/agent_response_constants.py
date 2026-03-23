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


def get_booking_widget(language: str="en", programs: list[str]=None):
    """
    Returns an HTML string representing a Booking Widget.
    """

    if programs is None or programs == []:
        programs = ["emba", "iemba", "emba_x"]

    labels = {
        "en": {"header": "Book a Consultation", "sub": "Select an advisor to view their calendar:"},
        "de": {"header": "Termin vereinbaren", "sub": "Wählen Sie einen Berater für den Kalender:"}
    }
    txt = labels.get(language, labels["en"])

    base_params = "?hide_gdpr_banner=1&embed_type=Inline&embed_domain=1"
    advisors = [
        {
            "name": "Cyra von Müller (EMBA)",
            "url": f"https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg{base_params}",
            "program": "emba"
        },
        {
            "name": "Kristin Fuchs (IEMBA)",
            "url": f"https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation{base_params}",
            "program": "iemba"
        },
        {
            "name": "Teyuna Giger (emba X)",
            "url": f"https://calendly.com/teyuna-giger-unisg{base_params}",
            "program": "emba_x"
        },
    ]

    html_content = f"""
    <div style="width: 100%; min-width: 100%; box-sizing: border-box; background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin-top: 10px; font-family: sans-serif;">
        <h3 style="margin: 0 0 10px 0; color: #111827; font-size: 1.2em;">{txt['header']}</h3>
        <p style="margin: 0 0 20px 0; color: #6b7280; font-size: 1em;">{txt['sub']}</p>
    """

    for advisor in advisors:
        if advisor["program"] in programs:
            html_content += f"""
            <details style="margin-bottom: 12px; border: 1px solid #d1d5db; border-radius: 8px; background: white; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <summary style="cursor: pointer; padding: 16px 20px; background-color: #ffffff; font-weight: 600; color: #374151; font-size: 1.05em; list-style: none; transition: background 0.2s;">
                    {advisor['name']}
                </summary>
                <div style="padding: 0; border-top: 1px solid #e5e7eb;">
                    <iframe src="{advisor['url']}" width="100%" height="650px" frameborder="0" style="display: block;"></iframe>
                </div>
            </details>
            """

    html_content += "</div>"
    return html_content


def get_disclaimer_widget(language: str = "en"):
    """
    Returns an HTML string representing a warning disclaimer.
    """
    disclaimers = {
        "en": {
            "title": "Disclaimer",
            "body": "Assessments provided by this advisor are non-binding and based on limited information. Please consult our program directors for final admission or credit evaluations."
        },
        "de": {
            "title": "Haftungsausschluss",
            "body": "Die Einschätzungen dieses Beraters sind unverbindlich und basieren auf begrenzten Informationen. Bitte wenden Sie sich für endgültige Zulassungs- oder Anrechnungsfragen an die Programmleitung."
        }
    }

    content = disclaimers.get(language, disclaimers["en"])

    # Yellow styling constants
    bg_color = "#fffbeb"  # Light yellow
    border_color = "#f59e0b"  # Amber/Yellow border
    icon_color = "#d97706"  # Darker amber for the icon
    text_color = "#92400e"  # Dark brown/yellow for readability

    html_content = f"""
    <div style="display: flex; align-items: flex-start; background-color: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 16px; margin-bottom: 20px; font-family: sans-serif;">
        <div style="margin-right: 12px; margin-top: 2px;">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{icon_color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
        </div>
        <div>
            <strong style="display: block; color: {text_color}; margin-bottom: 4px; font-size: 0.95em;">{content['title']}</strong>
            <p style="margin: 0; color: {text_color}; font-size: 0.85em; line-height: 1.4;">
                {content['body']}
            </p>
        </div>
    </div>
    """
    return html_content
