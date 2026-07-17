# Consent short text v1.1 (2026-07-17). Full consent statement lives on the
# linked subpage; the German version is authoritative.
PRIVACY_NOTICE = {
    "de": """
**Pilotphase bis 31.08.2026**

### Einwilligung zur Datenverarbeitung

Dieser Chatbot berät Sie zu den **Executive-MBA-Programmen der Universität St.Gallen**. Wenn Sie zustimmen, verarbeiten wir:

- Ihre **Chat-Eingaben** — sie werden zur Antworterzeugung an einen KI-Dienstleister in den **USA** (OpenRouter) übermittelt und bei uns nicht im Wortlaut gespeichert
- ein **Beratungsprofil** aus Ihren Angaben (z. B. Berufserfahrung, Interessen) — Speicherung in Deutschland, Löschung nach **30 Tagen**
- bei Terminbuchung: Name und E-Mail direkt beim Buchungsdienst **Calendly** (USA)

Ihre Daten dienen ausschliesslich der Studienberatung — kein Tracking, keine Werbung, kein KI-Training.
Die Einwilligung ist freiwillig; Sie können sie **jederzeit widerrufen** (emba@unisg.ch). Bitte geben Sie keine sensiblen Daten ein.

[Vollständige Einwilligungserklärung und Ihre Rechte](https://emba.unisg.ch/chatbot-test-consent-de)
""",

    "en": """
**Pilot phase until 31 August 2026**

### Consent to data processing

This chatbot advises you on the **Executive MBA programmes at the University of St.Gallen**. If you accept, we process:

- your **chat input** — transmitted to an AI service provider in the **USA** (OpenRouter) to generate answers; we do not store its wording
- an **advisory profile** derived from your input (e.g. professional experience, interests) — stored in Germany, deleted after **30 days**
- if you book an appointment: name and email directly with the booking service **Calendly** (USA)

Your data is used solely for study advisory purposes — no tracking, no advertising, no AI training.
Consent is voluntary and can be **withdrawn at any time** (emba@unisg.ch). Please do not enter sensitive personal data.

[Full consent statement and your rights](https://emba.unisg.ch/chatbot-test-consent-en)
"""
}

ACCEPT = {
    "de": "Zustimmen",
    "en": "Accept"
}

DECLINE = {
    "de": "Ablehnen",
    "en": "Decline"
}

DECLINE_MESSAGE = {
    "de": "Ohne Ihre Einwilligung können wir Sie leider nicht beraten. Bitte kontaktieren Sie uns direkt unter emba@unisg.ch.",
    "en": "Without your consent, we cannot provide advice. Please contact us directly at emba@unisg.ch.",
}

BOOK_TEXT = {
    "de": "Termin buchen",
    "en": "Book an appointment"
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

# hide_event_type_details removes Calendly's photo/title/description header —
# advisor and programme are already on the button the user just clicked.
# Do NOT set primary_color: ANY custom value (even Calendly's own default
# blue) switches available days to filled circles with tone-on-tone digits —
# unreadable. Verified 2026-07-12 via headless-Chrome renders; only the
# parameterless default (pale chips, dark digits) is legible.
BASE_BOOKING_PARAMS = (
    "?hide_gdpr_banner=1&embed_type=Inline"
    "&embed_domain=chatbot.emba.unisg.ch&hide_event_type_details=1"
)

EMBA = next(a for a in ADVISOR_CONTACTS if a["program"] == "emba")
IEMBA = next(a for a in ADVISOR_CONTACTS if a["program"] == "iemba")
EMBAX = next(a for a in ADVISOR_CONTACTS if a["program"] == "emba_x")

EMBA_URL = EMBA["url"] + BASE_BOOKING_PARAMS
IEMBA_URL = IEMBA["url"] + BASE_BOOKING_PARAMS
EMBAX_URL = EMBAX["url"] + BASE_BOOKING_PARAMS

BOOKING_WIDGET_HTML = {
    "en": f"""
<div style="width:100%; box-sizing:border-box; background:#f8f8f8; border:1px solid #d8d8d8; border-radius:8px; padding:12px; margin-top:10px; font-family:sans-serif;">
    <details>
        <summary style="cursor:pointer; font-weight:700; font-size:1.05rem; color:#404040;">
            {BOOK_TEXT["en"]}
        </summary>
        <p style="color:#666666; margin:10px 0 12px 0;">Choose an advisor:</p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
            <button onclick="document.getElementById('booking-frame-en').src='{EMBA_URL}'; document.getElementById('booking-frame-en').style.display='block';" style="cursor:pointer; padding:6px 12px; border:none; border-radius:4px; background:#008435; color:white; font-weight:600;">{EMBA["name"]}</button>
            <button onclick="document.getElementById('booking-frame-en').src='{IEMBA_URL}'; document.getElementById('booking-frame-en').style.display='block';" style="cursor:pointer; padding:6px 12px; border:none; border-radius:4px; background:#008435; color:white; font-weight:600;">{IEMBA["name"]}</button>
            <button onclick="document.getElementById('booking-frame-en').src='{EMBAX_URL}'; document.getElementById('booking-frame-en').style.display='block';" style="cursor:pointer; padding:6px 12px; border:none; border-radius:4px; background:#008435; color:white; font-weight:600;">{EMBAX["name"]}</button>
        </div>
        <iframe id="booking-frame-en" src="" width="100%" height="520" frameborder="0" style="display:none; width:100%; border:none; border-radius:6px; background:white;"></iframe>
    </details>
</div>
""",
    "de": f"""
<div style="width:100%; box-sizing:border-box; background:#f8f8f8; border:1px solid #d8d8d8; border-radius:8px; padding:12px; margin-top:10px; font-family:sans-serif;">
    <details>
        <summary style="cursor:pointer; font-weight:700; font-size:1.05rem; color:#404040;">
            {BOOK_TEXT["de"]}
        </summary>
        <p style="color:#666666; margin:10px 0 12px 0;">Wählen Sie einen Berater:</p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
            <button onclick="document.getElementById('booking-frame-de').src='{EMBA_URL}'; document.getElementById('booking-frame-de').style.display='block';" style="cursor:pointer; padding:6px 12px; border:none; border-radius:4px; background:#008435; color:white; font-weight:600;">{EMBA["name"]}</button>
            <button onclick="document.getElementById('booking-frame-de').src='{IEMBA_URL}'; document.getElementById('booking-frame-de').style.display='block';" style="cursor:pointer; padding:6px 12px; border:none; border-radius:4px; background:#008435; color:white; font-weight:600;">{IEMBA["name"]}</button>
            <button onclick="document.getElementById('booking-frame-de').src='{EMBAX_URL}'; document.getElementById('booking-frame-de').style.display='block';" style="cursor:pointer; padding:6px 12px; border:none; border-radius:4px; background:#008435; color:white; font-weight:600;">{EMBAX["name"]}</button>
        </div>
        <iframe id="booking-frame-de" src="" width="100%" height="520" frameborder="0" style="display:none; width:100%; border:none; border-radius:6px; background:white;"></iframe>
    </details>
</div>
""",
}
