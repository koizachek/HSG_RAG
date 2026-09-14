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

# Advisor buttons: the clicked button turns into the "selected" style and the
# others reset, so the user can see which advisor's calendar is open. Pilot
# feedback August 2026: "man sieht nicht, auf welchem Profil man sich
# befindet" and re-clicking the same advisor appeared to do nothing.
_BTN_BASE = "cursor:pointer; padding:6px 12px; border:2px solid #008435; border-radius:4px; font-weight:600;"
_BTN_IDLE = "background:#008435; color:white;"
_BTN_ACTIVE = "background:white; color:#008435;"


def _advisor_button(lang: str, advisor: dict, url: str, active: bool = False) -> str:
    frame = f"booking-frame-{lang}"
    onclick = (
        "var b=this.parentNode.children;"
        f"for(var i=0;i<b.length;i++){{b[i].style.background='#008435';b[i].style.color='white';}}"
        "this.style.background='white';this.style.color='#008435';"
        f"var f=document.getElementById('{frame}');"
        f"if(f.src!=='{url}'){{f.src='{url}';}}"
        "f.style.display='block';"
        "f.scrollIntoView({behavior:'smooth',block:'nearest'});"
    )
    style = _BTN_ACTIVE if active else _BTN_IDLE
    return (
        f'<button onclick="{onclick}" style="{_BTN_BASE} {style}">'
        f'{advisor["name"]}</button>'
    )


_ADVISORS_BY_PROGRAM = {
    "emba": (EMBA, EMBA_URL),
    "iemba": (IEMBA, IEMBA_URL),
    "emba_x": (EMBAX, EMBAX_URL),
}


def _booking_widget_html(lang: str, choose_text: str, programs: list[str] | None = None) -> str:
    """
    Render the booking section. With ``programs`` (canonical ids) only the
    matching advisors are offered; a single advisor is pre-selected, the
    section is expanded and her calendar is loaded straight away. Without
    ``programs`` all three advisors are offered (static default after consent).
    """
    selected = [
        _ADVISORS_BY_PROGRAM[p] for p in (programs or []) if p in _ADVISORS_BY_PROGRAM
    ] or list(_ADVISORS_BY_PROGRAM.values())
    single = len(selected) == 1
    buttons = "\n            ".join(
        _advisor_button(lang, advisor, url, active=single)
        for advisor, url in selected
    )
    details_open = " open" if single else ""
    frame_src = selected[0][1] if single else ""
    frame_display = "block" if single else "none"
    return f"""
<div style="width:100%; box-sizing:border-box; background:#f8f8f8; border:1px solid #d8d8d8; border-radius:8px; padding:12px; margin-top:10px; font-family:sans-serif;">
    <details{details_open}>
        <summary style="cursor:pointer; font-weight:700; font-size:1.05rem; color:#404040;">
            {BOOK_TEXT[lang]}
        </summary>
        <p style="color:#666666; margin:10px 0 12px 0;">{choose_text}</p>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
            {buttons}
        </div>
        <iframe id="booking-frame-{lang}" src="{frame_src}" width="100%" height="520" frameborder="0" style="display:{frame_display}; width:100%; border:none; border-radius:6px; background:white;"></iframe>
    </details>
</div>
"""


_CHOOSE_TEXT = {"en": "Choose an advisor:", "de": "Wählen Sie eine Beraterin:"}


def booking_widget_for(lang: str, programs: list[str] | None) -> str:
    """Booking section for a booking turn: only the advisor(s) of ``programs``."""
    lang = lang if lang in _CHOOSE_TEXT else "en"
    return _booking_widget_html(lang, _CHOOSE_TEXT[lang], programs)


BOOKING_WIDGET_HTML = {
    "en": _booking_widget_html("en", _CHOOSE_TEXT["en"]),
    "de": _booking_widget_html("de", _CHOOSE_TEXT["de"]),
}
