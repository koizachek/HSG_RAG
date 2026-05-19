import re

from langchain_core.messages import AIMessage

def extract_experience_years(conversation: str) -> int | None:
    """Extract years of professional experience from conversation text."""
    # Look for patterns like "10 years", "5 years experience", etc.
    patterns = [
        r'(\d+)\s*years?\s*(?:of\s*)?(?:experience|work)',
        r'(\d+)\s*years?\s*in\s*(?:the\s*)?(?:field|industry)',
        r'working\s*for\s*(\d+)\s*years?',
        r'(\d+)\s*Jahre\s*(?:Erfahrung|Berufserfahrung)',  # German
    ]
    for pattern in patterns:
        match = re.search(pattern, conversation, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None

def extract_leadership_years(conversation: str) -> int | None:
    """Extract years of leadership experience from conversation text."""
    patterns = [
        r'(\d+)\s*years?\s*(?:of\s*)?(?:leadership|management|managing)',
        r'(?:lead|led|manage|managed)\s*(?:for\s*)?(\d+)\s*years?',
        r'(\d+)\s*Jahre\s*(?:Führungserfahrung|Führung)',  # German
    ]
    for pattern in patterns:
        match = re.search(pattern, conversation, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None

def extract_field(conversation: str) -> str | None:
    """Extract professional field/industry from conversation text."""
    # Common fields mentioned in executive education
    fields = [
        'finance', 'banking', 'technology', 'tech', 'IT', 'healthcare',
        'consulting', 'manufacturing', 'retail', 'marketing', 'sales',
        'engineering', 'pharma', 'telecommunications', 'energy',
        'Finanzwesen', 'Technologie', 'Gesundheitswesen', 'Beratung'  # German
    ]
    conversation_lower = conversation.lower()
    for field in fields:
        if field.lower() in conversation_lower:
            return field.capitalize()
    return None

def extract_interest(conversation: str) -> str | None:
    """Extract content interests from conversation text."""
    # Look for interest indicators
    interests = [
        'strategy', 'innovation', 'leadership', 'digital transformation',
        'finance', 'operations', 'marketing', 'entrepreneurship',
        'social impact', 'technology', 'management',
        'Strategie', 'Innovation', 'Führung', 'Digitalisierung'  # German
    ]
    conversation_lower = conversation.lower()
    found_interests = [interest for interest in interests
                       if interest.lower() in conversation_lower]
    return ', '.join(found_interests) if found_interests else None

def extract_name(conversation: str) -> str | None:
    """Extract user's name from conversation text."""
    patterns = [
        r"(?:my name is|i'm|i am|call me)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"(?:this is|it's)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"(?:ich heiße|mein Name ist|ich bin)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",  # German
    ]
    for pattern in patterns:
        match = re.search(pattern, conversation, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Filter out common words that might be误ly matched
            excluded = ['interested', 'looking', 'working', 'searching', 'asking']
            if name.lower() not in excluded:
                return name
    return None

def detect_handover_request(conversation: str) -> bool:
    """Detect if user requested appointment, callback, or contact."""
    # Keywords indicating handover request
    handover_keywords = [
        'appointment', 'call me', 'contact me', 'schedule', 'meeting',
        'callback', 'reach out', 'follow up', 'get in touch', 'speak with',
        'talk to', 'consultation', 'discuss with', 'meet with',
        'Termin', 'Rückruf', 'kontaktieren', 'Gespräch', 'anrufen',  # German
        'zurückrufen', 'Beratung', 'treffen'
    ]
    conversation_lower = conversation.lower()
    return any(keyword.lower() in conversation_lower for keyword in handover_keywords)

def previous_response_offered_booking(conversation_history) -> bool:
    """Return True if the latest assistant turn offered booking as a next step."""
    booking_offer_terms = [
        "appointment slots",
        "book an appointment",
        "book a consultation",
        "appointment booking",
        "show you available appointments",
        "show appointment options",
        "terminbuchung",
        "termin buchen",
        "termine anzeigen",
        "verfügbare termine",
        "beratungstermin",
    ]

    for message in reversed(conversation_history):
        if not isinstance(message, AIMessage):
            continue
        content = getattr(message, "content", "") or getattr(message, "text", "")
        if isinstance(content, list):
            content = " ".join(str(part) for part in content)
        content_lower = str(content).lower()
        return any(term in content_lower for term in booking_offer_terms)

    return False

def get_latest_ai_message_content(conversation_history, skip_latest: bool = False) -> str:
    """Return the latest assistant message content from conversation history."""
    ai_messages_seen = 0

    for message in reversed(conversation_history):
        if not isinstance(message, AIMessage):
            continue

        ai_messages_seen += 1
        if skip_latest and ai_messages_seen == 1:
            continue

        content = getattr(message, "content", "") or getattr(message, "text", "")
        if isinstance(content, list):
            return " ".join(str(part) for part in content)
        return str(content)

    return ""

def is_booking_preference_follow_up(query: str) -> bool:
    """Detect short follow-up answers that continue an active booking flow."""
    query_lower = query.lower().strip()
    if not query_lower:
        return False

    preference_terms = [
        "online",
        "on-site",
        "onsite",
        "in person",
        "in-person",
        "st.gallen",
        "st. gallen",
        "morning",
        "mornings",
        "afternoon",
        "afternoons",
        "evening",
        "beginning of the week",
        "start of the week",
        "end of the week",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "morgens",
        "vormittag",
        "vormittags",
        "nachmittag",
        "nachmittags",
        "abends",
        "wochenanfang",
        "anfang der woche",
        "ende der woche",
        "montag",
        "dienstag",
        "mittwoch",
        "donnerstag",
        "freitag",
        "vor ort",
        "vor-ort",
        "persönlich",
        "persoenlich",
        "hybrid",
    ]

    if any(term in query_lower for term in preference_terms):
        return True

    return False

def previous_response_requested_booking_preferences(conversation_history) -> bool:
    """Return True when the previous assistant turn asked clarifying booking questions."""
    content_lower = get_latest_ai_message_content(conversation_history).lower()
    if not content_lower:
        return False

    booking_context_terms = [
        "appointment options",
        "available appointments",
        "available slots",
        "appointment slots",
        "online-terminoptionen",
        "terminoptionen",
        "verfügbare slots",
        "verfügbare termine",
        "beratungsgespräch",
        "beratung",
    ]
    clarification_terms = [
        "do you prefer",
        "would you prefer",
        "which programme",
        "which program",
        "one short question",
        "final question",
        "when i know this",
        "bitte noch kurz",
        "eine kurze rückfrage",
        "eine kurze letzte frage",
        "bevorzugen sie",
        "haben sie eine tagespräferenz",
        "sobald ich das weiss",
        "damit die slots besser passen",
    ]

    return (
        any(term in content_lower for term in booking_context_terms)
        and any(term in content_lower for term in clarification_terms)
    )

def response_commits_to_showing_booking_widget(response: str) -> bool:
    """Detect when the assistant says booking options are being shown now."""
    response_lower = response.lower()

    positive_terms = [
        "i can show you",
        "contact details and available appointment slots are shown below",
        "appointment options are shown below",
        "available slots are shown below",
        "i can now show you",
        "ich kann ihnen nun",
        "ich kann ihnen jetzt",
        "unten werden ihnen",
        "unten finden sie",
        "unten sehen sie",
        "terminoptionen anzeigen",
        "verfügbaren slots",
        "verfügbaren termine",
    ]
    defer_terms = [
        "if you would like",
        "if you later wish",
        "you can ask me",
        "if that would be helpful",
        "sobald ich das weiss",
        "wenn ich das weiss",
        "damit die slots besser passen",
        "bitte noch kurz",
        "eine kurze rückfrage",
        "eine kurze letzte frage",
        "bevorzugen sie",
        "have you got a preference",
        "do you prefer",
        "would you prefer",
        "which programme",
        "which program",
    ]

    return (
        any(term in response_lower for term in positive_terms)
        and not any(term in response_lower for term in defer_terms)
    )

def is_explicit_booking_intent(conversation_history, query: str) -> bool:
    """Detect whether the user is actively asking to book or accepting a booking offer."""
    query_lower = query.lower()
    direct_booking_terms = [
        "book",
        "schedule",
        "appointment",
        "consultation",
        "need a consultation",
        "personal consultation",
        "speak with",
        "talk to an advisor",
        "talk to admissions",
        "connect me",
        "show me available",
        "show appointment",
        "available slots",
        "termin",
        "termin buchen",
        "termin vereinbaren",
        "beratungstermin",
        "beratungsgespräch",
        "ich brauche eine beratung",
        "ich möchte eine beratung",
        "ich will eine beratung",
        "beratung für",
        "persönliche beratung",
        "persoenliche beratung",
        "mit jemandem sprechen",
        "mit admissions sprechen",
        "mit der zulassung sprechen",
        "termine anzeigen",
        "verfügbare termine",
    ]
    rejection_terms = [
        "do not want",
        "don't want",
        "no appointment",
        "not book",
        "not schedule",
        "no thanks",
        "no thank you",
        "kein termin",
        "keinen termin",
        "keine beratung",
        "nicht buchen",
        "nicht vereinbaren",
        "nein danke",
    ]
    acceptance_terms = [
        "yes",
        "yes please",
        "please do",
        "that would be helpful",
        "show me",
        "ja",
        "ja bitte",
        "gerne",
        "bitte",
        "mach das",
        "zeige",
    ]

    def contains_term(term: str) -> bool:
        if term in {"yes", "ja", "bitte"}:
            return re.search(rf"\b{re.escape(term)}\b", query_lower) is not None
        return term in query_lower

    if any(contains_term(term) for term in rejection_terms):
        return False

    if any(contains_term(term) for term in direct_booking_terms):
        return True

    return (
        previous_response_offered_booking(conversation_history)
        and any(contains_term(term) for term in acceptance_terms)
    )

def determine_suggested_program(state) -> str | None:
    """Determine recommended program based on user profile."""

    # If program interest was explicitly mentioned
    if state['program_interest']:
        return state['program_interest'][0]

    # Make recommendation based on profile
    experience = state.get('experience_years', 0) or 0
    leadership = state.get('leadership_years', 0) or 0

    # EMBA: 5+ years experience, 2+ years leadership
    if experience >= 5 and leadership >= 2:
        return 'EMBA'
    # IEMBA: International focus, 3+ years experience
    elif experience >= 3:
        return 'IEMBA'
    # EMBA X: Digital/Innovation focus
    elif state.get('interest') and any(kw in state.get('interest', '').lower()
                                       for kw in ['digital', 'innovation', 'technology']):
        return 'emba X'

    return None

