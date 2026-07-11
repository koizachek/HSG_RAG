PRIVACY_NOTICE = {
    "de": """
**Pilotphase bis 31.08.26**

### Datenschutzhinweis

Wir verwenden Ihre Angaben, um Sie zu **Executive MBA Programmen der Universität St.Gallen** zu beraten.  
Dabei verarbeiten wir insbesondere:

- Ihre Gesprächsinhalte und Anfragen  
- Kontaktdaten (Name, E-Mail) bei Terminbuchung  
- Informationen zu Ihrer Berufserfahrung und Ausbildung  

Ihre Daten werden **ausschließlich für die Studienberatung** verwendet und **nicht an Dritte weitergegeben**.  
Sie können Ihre Einwilligung **jederzeit widerrufen**, indem Sie uns kontaktieren.

[Weitere Informationen zur Datenschutzerklärung](https://www.unisg.ch/en/data-protection-declaration/)
""",

    "en": """
**Pilot phase until 31 August 2026**

### Privacy Notice

We use your information to advise you on **Executive MBA programmes at the University of St.Gallen**.  
We process in particular:

- Your conversation content and inquiries  
- Contact details (name, email) for appointment booking  
- Information about your professional experience and education  

Your data is used **solely for study advisory purposes** and **is not shared with third parties**.  
You may **withdraw your consent at any time** by contacting us.

[More information in the Privacy Policy](https://www.unisg.ch/en/data-protection-declaration/)
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
