"""
Conversation state management: user profile extraction and tracking.

Adopted from the chatbot-decoupling branch: this logic previously lived inside
the ExecutiveAgentChain class; extracting it keeps the chain a thin
orchestrator. Latency-neutral — pure regex/keyword extraction, no LLM calls.
"""
import json
import os
import re
from datetime import datetime

from langchain_core.messages import AIMessage

from src.config import config
from src.utils.logging import get_logger

logger = get_logger('conversation_state')


class ConversationStateManager:
    """Extracts and tracks user profile data from conversation turns.

    Holds a reference to the owning chain and operates on its
    `_conversation_state` dict and `_conversation_history` list.
    """

    def __init__(self, chain) -> None:
        self._chain = chain

    # ------------------------------ public API ------------------------------

    def update(self, user_query: str, agent_response: str) -> None:
        """Update conversation state by extracting information from the turn."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        state = self._chain._conversation_state

        # Extract profile information only from the user's own text. Assistant
        # programme descriptions must not become inferred user interests.
        profile_text = user_query

        if not state.get('experience_years'):
            exp_years = self._extract_experience_years(profile_text)
            if exp_years:
                state['experience_years'] = exp_years
                logger.info(f"Extracted experience years: {exp_years}")

        if not state.get('leadership_years'):
            lead_years = self._extract_leadership_years(profile_text)
            if lead_years:
                state['leadership_years'] = lead_years
                logger.info(f"Extracted leadership years: {lead_years}")

        if not state.get('field'):
            field = self._extract_field(profile_text)
            if field:
                state['field'] = field
                logger.info(f"Extracted field: {field}")

        if not state.get('interest'):
            interest = self._extract_interest(profile_text)
            if interest:
                state['interest'] = interest
                logger.info(f"Extracted interest: {interest}")

        if not state.get('user_name'):
            name = self._extract_name(profile_text)
            if name:
                state['user_name'] = name
                logger.info(f"Extracted name: {name}")

        # Detect handover request from the user only; assistant soft offers
        # should not count.
        if self._detect_handover_request(user_query):
            state['handover_requested'] = True
            logger.info("Handover request detected")

        # Check for programme mentions. Match the most specific names first so
        # "emba X" is not misclassified as the generic EMBA HSG.
        user_programmes = self._chain._extract_programmes_from_text(user_query)
        for program in user_programmes:
            if program not in state['program_interest']:
                state['program_interest'].append(program)

        if len(user_programmes) == 1:
            state['suggested_program'] = user_programmes[0]
            logger.info(f"Suggested program updated from user selection: {user_programmes[0]}")

        suggested = self._determine_suggested_program()
        if suggested and not state.get('suggested_program'):
            state['suggested_program'] = suggested
            logger.info(f"Suggested program: {suggested}")

    def log_user_profile(self) -> None:
        """Log user profile to a JSON file."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        state = self._chain._conversation_state
        try:
            log_dir = os.path.join('logs', 'user_profiles')
            os.makedirs(log_dir, exist_ok=True)

            profile_data = {
                'session_id': state['session_id'],
                'user_id': state['user_id'],
                'name': state.get('user_name'),
                'timestamp': datetime.now().isoformat(),
                'experience_years': state.get('experience_years'),
                'leadership_years': state.get('leadership_years'),
                'field': state.get('field'),
                'interest': state.get('interest'),
                'suggested_program': state.get('suggested_program'),
                'handover': state.get('handover_requested'),
                'user_language': state.get('user_language'),
                'program_interest': state.get('program_interest', []),
            }

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(log_dir, f'profile_{state["user_id"]}_{timestamp}.json')

            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)

            logger.info(f"User profile logged to {log_file}")
        except Exception as e:
            logger.error(f"Failed to log user profile: {e}")

    # ----------------------------- derivations ------------------------------

    def _determine_suggested_program(self) -> str | None:
        """Determine recommended programme based on the user profile."""
        state = self._chain._conversation_state

        # If programme interest was explicitly mentioned
        if state['program_interest']:
            return self._chain._normalise_programme_id(state['program_interest'][0])

        if state.get('interest') and any(
            kw in state.get('interest', '').lower()
            for kw in ['digital', 'digitalisierung', 'innovation', 'technology', 'technologie']
        ):
            return 'emba_x'

        # Do not infer programme fit from years of experience in code. Current
        # eligibility thresholds live in the scraped programme source.
        return None

    def previous_response_offered_booking(self) -> bool:
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

        for message in reversed(self._chain._conversation_history):
            if not isinstance(message, AIMessage):
                continue
            content = getattr(message, "content", "") or getattr(message, "text", "")
            if isinstance(content, list):
                content = " ".join(str(part) for part in content)
            content_lower = str(content).lower()
            return any(term in content_lower for term in booking_offer_terms)

        return False

    # ------------------------- pure text extraction -------------------------

    @staticmethod
    def _extract_experience_years(conversation: str) -> int | None:
        """Extract years of professional experience from conversation text."""
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

    @staticmethod
    def _extract_leadership_years(conversation: str) -> int | None:
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

    @staticmethod
    def _extract_field(conversation: str) -> str | None:
        """Extract professional field/industry from conversation text."""
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

    @staticmethod
    def _extract_interest(conversation: str) -> str | None:
        """Extract content interests from conversation text."""
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

    @staticmethod
    def _extract_name(conversation: str) -> str | None:
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
                excluded = ['interested', 'looking', 'working', 'searching', 'asking']
                if name.lower() not in excluded:
                    return name
        return None

    @staticmethod
    def _detect_handover_request(conversation: str) -> bool:
        """Detect if the user requested an appointment, callback, or contact."""
        handover_keywords = [
            'appointment', 'call me', 'contact me', 'schedule', 'meeting',
            'callback', 'reach out', 'follow up', 'get in touch', 'speak with',
            'talk to', 'consultation', 'discuss with', 'meet with',
            'Termin', 'Rückruf', 'kontaktieren', 'Gespräch', 'anrufen',  # German
            'zurückrufen', 'Beratung', 'treffen'
        ]
        conversation_lower = conversation.lower()
        return any(keyword.lower() in conversation_lower for keyword in handover_keywords)
