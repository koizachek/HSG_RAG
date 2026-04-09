""" Constants for Gradio app """

GREETING_MESSAGES = {
    "en": [
        "Hello and welcome. I am your Executive Education Advisor for the HSG Executive MBA programmes (**IEMBA**, **emba X**, and **EMBA**). How may I support your MBA planning today?",
        "Hello and welcome. I am your Executive Education Advisor for the University of St.Gallen Executive MBA programmes (**IEMBA**, **emba X**, and **EMBA**). How may I assist you with your programme search?",
        "Hello and welcome. I am here to help you explore the University of St.Gallen Executive MBA programmes (**EMBA**, **IEMBA**, and **emba X**). What would you like to discuss today?",
        "Hello and welcome. I am your Executive Education Advisor for the University of St.Gallen’s Executive MBA programmes, and I am here to help you assess fit across **EMBA**, **IEMBA**, and **emba X**.",
        "Hello and welcome. I am here to support you with questions about the University of St.Gallen Executive MBA programmes and to help you evaluate the **EMBA**, **IEMBA**, and **emba X** options.",
    ],
    "de": [
        "Guten Tag. Ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme und unterstütze Sie gerne bei Fragen zu **EMBA**, **IEMBA** und **emba X**.",
        "Guten Tag. Ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme (**EMBA**, **IEMBA**, **emba X**). Ich unterstütze Sie bei Programmwahl, Ablauf und Zulassungsfragen.",
        "Guten Tag und herzlich willkommen. Ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme und unterstütze Sie gerne bei Fragen zu **EMBA**, **IEMBA** und **emba X**.",
        "Guten Tag. Ich bin Ihr Executive-Education-Berater für die HSG Executive MBA Programme (**EMBA**, **IEMBA**, **emba X**) und unterstütze Sie gerne bei der Einschätzung der passenden Option.",
        "Guten Tag. Ich unterstütze Sie gerne bei Fragen zu den HSG Executive MBA Programmen und helfe Ihnen, die Optionen **EMBA**, **IEMBA** und **emba X** einzuordnen.",
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
        "I am sorry, but I could not find sufficiently reliable information in my records to answer that question with confidence. "
        "Could you please rephrase your question?\n\n"
        "Alternatively, you may book a consultation with an admissions advisor using the contact details and links below."
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
        "You can book an appointment with an admissions advisor using the contact details and links below. "
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

ADMISSIONS_TEAM_CONTACT = {
    "en": {
        "email": "emba@unisg.ch",
        "phone": "+41 71 224 27 02",
    },
    "de": {
        "email": "emba@unisg.ch",
        "phone": "+41 71 224 27 02",
    },
}

ADVISOR_CONTACTS = [
    {
        "name": "Cyra von Müller (EMBA)",
        "program": "emba",
        "email": "cyra.vonmueller@unisg.ch",
        "phone": "+41 71 224 27 12",
        "url": "https://calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg",
    },
    {
        "name": "Kristin Fuchs (IEMBA)",
        "program": "iemba",
        "email": "kristin.fuchs@unisg.ch",
        "phone": "+41 71 224 75 46",
        "url": "https://calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation",
    },
    {
        "name": "Teyuna Giger (emba X)",
        "program": "emba_x",
        "email": "teyuna.giger@unisg.ch",
        "phone": "+41 71 224 77 65",
        "url": "https://calendly.com/teyuna-giger-unisg",
    },
]


def get_admissions_contact_text(language: str = "en") -> str:
    labels = {
        "en": "You can reach the Executive MBA admissions team at {email} or {phone}.",
        "de": "Sie erreichen das Executive-MBA-Zulassungsteam unter {email} oder {phone}.",
    }
    contact = ADMISSIONS_TEAM_CONTACT.get(language, ADMISSIONS_TEAM_CONTACT["en"])
    template = labels.get(language, labels["en"])
    return template.format(email=contact["email"], phone=contact["phone"])


def get_booking_widget(language: str="en", programs: list[str]=None):
    """
    Returns an HTML string representing a Booking Widget.
    """

    if programs is None or programs == []:
        programs = ["emba", "iemba", "emba_x"]

    labels = {
        "en": {
            "header": "Book a Consultation",
            "sub": "Select an advisor to view available appointment slots and contact details:",
            "email": "Email",
            "phone": "Phone",
        },
        "de": {
            "header": "Termin vereinbaren",
            "sub": "Wählen Sie einen Berater, um verfügbare Termine und Kontaktdaten zu sehen:",
            "email": "E-Mail",
            "phone": "Telefon",
        }
    }
    txt = labels.get(language, labels["en"])

    base_params = "?hide_gdpr_banner=1&embed_type=Inline&embed_domain=1"

    html_content = f"""
    <div style="width: 100%; min-width: 100%; box-sizing: border-box; background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin-top: 10px; font-family: sans-serif;">
        <h3 style="margin: 0 0 10px 0; color: #111827; font-size: 1.2em;">{txt['header']}</h3>
        <p style="margin: 0 0 20px 0; color: #6b7280; font-size: 1em;">{txt['sub']}</p>
    """

    for advisor in ADVISOR_CONTACTS:
        if advisor["program"] in programs:
            html_content += f"""
            <details style="margin-bottom: 12px; border: 1px solid #d1d5db; border-radius: 8px; background: white; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                <summary style="cursor: pointer; padding: 16px 20px; background-color: #ffffff; font-weight: 600; color: #374151; font-size: 1.05em; list-style: none; transition: background 0.2s;">
                    {advisor['name']}
                </summary>
                <div style="padding: 16px 20px 0 20px; border-top: 1px solid #e5e7eb;">
                    <p style="margin: 0 0 6px 0; color: #374151;"><strong>{txt['email']}:</strong> <a href="mailto:{advisor['email']}" style="color: #1d4ed8; text-decoration: none;">{advisor['email']}</a></p>
                    <p style="margin: 0 0 16px 0; color: #374151;"><strong>{txt['phone']}:</strong> <a href="tel:{advisor['phone'].replace(' ', '')}" style="color: #1d4ed8; text-decoration: none;">{advisor['phone']}</a></p>
                </div>
                <div style="padding: 0; border-top: 1px solid #e5e7eb;">
                    <iframe src="{advisor['url']}{base_params}" width="100%" height="650px" frameborder="0" style="display: block;"></iframe>
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
