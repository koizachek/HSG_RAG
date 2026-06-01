import glob
import json
import os
import re
from datetime import datetime

from src.config import config
from src.rag.chain_components import ChainComponent
from src.utils.logging import get_logger

chain_logger = get_logger('agent_chain')


class ConversationStateManager(ChainComponent):
    def _extract_experience_years(self, conversation: str) -> int | None:
        """Extract years of professional experience from conversation text."""
        # Look for patterns like "10 years", "5 years experience", etc.
        patterns = [
            r'(\d+)\s*years?\s*(?:of\s*)?(?:experience|work)',
            r'(\d+)\s*years?\s*in\s*(?:the\s*)?(?:field|industry)',
            r'working\s*for\s*(\d+)\s*years?',
            r'(\d+)\s*Jahre?n?\s*(?:Erfahrung|Berufserfahrung)',  # German
            r'(?:arbeite|tätig|taetig|berufstätig|berufstaetig|working)\s*(?:seit\s*)?(\d+)\s*Jahre?n?',
            r'seit\s*(\d+)\s*Jahre?n?\s*(?:berufstätig|berufstaetig|tätig|taetig|im beruf|in der branche)?',
        ]
        for pattern in patterns:
            match = re.search(pattern, conversation, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _extract_leadership_years(self, conversation: str) -> int | None:
        """Extract years of leadership experience from conversation text."""
        patterns = [
            r'(\d+)\s*years?\s*(?:of\s*)?(?:leadership|management|managing)',
            r'(?:lead|led|manage|managed)\s*(?:for\s*)?(\d+)\s*years?',
            r'(\d+)\s*Jahre?n?\s*(?:Führungserfahrung|Führung)',  # German
            r'davon\s*(\d+)\s*Jahre?n?\s*(?:als\s*)?(?:Abteilungsleiter|Teamleiter|Bereichsleiter|Leiter|Manager|Führungskraft)',
            r'(\d+)\s*Jahre?n?\s*(?:als\s*)?(?:Abteilungsleiter|Teamleiter|Bereichsleiter|Leiter|Manager|Führungskraft)',
        ]
        for pattern in patterns:
            match = re.search(pattern, conversation, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _extract_field(self, conversation: str) -> str | None:
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

    def _extract_interest(self, conversation: str) -> str | None:
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

    def _extract_name(self, conversation: str) -> str | None:
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

    def _detect_handover_request(self, conversation: str) -> bool:
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

    def _determine_suggested_program(self) -> str | None:
        """Determine recommended program based on user profile."""
        state = self._conversation_state

        # If program interest was explicitly mentioned
        if state['program_interest']:
            return self._normalise_programme_id(state['program_interest'][0])

        if state.get('interest') and any(kw in state.get('interest', '').lower()
                                         for kw in ['digital', 'digitalisierung', 'innovation', 'technology', 'technologie']):
            return 'emba_x'

        # Do not infer programme fit from years of experience in code. Current
        # eligibility thresholds live in the scraped programme source.
        return None

    def _update_conversation_state(self, user_query: str, agent_response: str) -> None:
        """Update conversation state by extracting information from the conversation."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        # Extract profile information only from the user's own text. Assistant
        # programme descriptions must not become inferred user interests.
        profile_text = user_query

        if not self._conversation_state.get('experience_years'):
            exp_years = self._extract_experience_years(profile_text)
            if exp_years:
                self._conversation_state['experience_years'] = exp_years
                chain_logger.info(f"Extracted experience years: {exp_years}")

        if not self._conversation_state.get('leadership_years'):
            lead_years = self._extract_leadership_years(profile_text)
            if lead_years:
                self._conversation_state['leadership_years'] = lead_years
                chain_logger.info(f"Extracted leadership years: {lead_years}")

        if not self._conversation_state.get('field'):
            field = self._extract_field(profile_text)
            if field:
                self._conversation_state['field'] = field
                chain_logger.info(f"Extracted field: {field}")

        if not self._conversation_state.get('interest'):
            interest = self._extract_interest(profile_text)
            if interest:
                self._conversation_state['interest'] = interest
                chain_logger.info(f"Extracted interest: {interest}")

        # Extract name
        if not self._conversation_state.get('user_name'):
            name = self._extract_name(profile_text)
            if name:
                self._conversation_state['user_name'] = name
                chain_logger.info(f"Extracted name: {name}")

        # Detect handover request from the user only; assistant soft offers should not count.
        if self._detect_handover_request(user_query):
            self._conversation_state['handover_requested'] = True
            chain_logger.info("Handover request detected")

        # Check for program mentions. Match the most specific names first so
        # "emba X" is not misclassified as the generic EMBA HSG.
        user_programmes = self._extract_programmes_from_text(user_query)
        for program in user_programmes:
            if program not in self._conversation_state['program_interest']:
                self._conversation_state['program_interest'].append(program)

        if len(user_programmes) == 1:
            self._conversation_state['suggested_program'] = user_programmes[0]
            chain_logger.info(f"Suggested program updated from user selection: {user_programmes[0]}")

        # Update suggested program
        suggested = self._determine_suggested_program()
        if suggested and not self._conversation_state.get('suggested_program'):
            self._conversation_state['suggested_program'] = suggested
            chain_logger.info(f"Suggested program: {suggested}")

    def _log_user_profile(self) -> None:
        """Log user profile to JSON file."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        try:
            # Create logs directory if it doesn't exist
            log_dir = os.path.join('logs', 'user_profiles')
            os.makedirs(log_dir, exist_ok=True)

            # Create profile data
            profile_data = {
                'session_id': self._conversation_state['session_id'],
                'user_id': self._conversation_state['user_id'],
                'name': self._conversation_state.get('user_name'),
                'timestamp': datetime.now().isoformat(),
                'experience_years': self._conversation_state.get('experience_years'),
                'leadership_years': self._conversation_state.get('leadership_years'),
                'field': self._conversation_state.get('field'),
                'interest': self._conversation_state.get('interest'),
                'suggested_program': self._conversation_state.get('suggested_program'),
                'handover': self._conversation_state.get('handover_requested'),
                'user_language': self._conversation_state.get('user_language'),
                'program_interest': self._conversation_state.get('program_interest', []),
            }

            # Log file path with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(log_dir, f'profile_{self._user_id}_{timestamp}.json')

            # Write to file
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)

            chain_logger.info(f"User profile logged to {log_file}")

        except Exception as e:
            chain_logger.error(f"Failed to log user profile: {e}")

    def reset_conversation_state(self) -> None:
        """Clear in-memory conversation state while keeping the same session id."""
        self._conversation_history = []
        self._pending_continuation = None
        self._programme_overview_detail_level = 0
        self._programme_overview_profile_context = False
        self._conversation_state.update({
            'user_language': None,
            'user_name': None,
            'experience_years': None,
            'leadership_years': None,
            'field': None,
            'interest': None,
            'qualification_level': None,
            'program_interest': [],
            'suggested_program': None,
            'handover_requested': None,
            'topics_discussed': [],
            'preferences_known': False
        })
        self._fallback_counters = {
            "invalid_input": 0,
            "aggressive": 0,
            "scope_violations": {},
        }

    def wipe_session_data(self) -> None:
        """Delete in-memory session data and on-disk profile files (GDPR withdrawal)."""

        # --- 1) In-memory wipe ---
        self.reset_conversation_state()

        # --- 2) On-disk wipe (delete profile_<user_id>_*.json) ---
        if not self._user_id:
            chain_logger.warning("wipe_session_data called without user_id – skipping file deletion")
            return

        pattern = os.path.join(
            "logs",
            "user_profiles",
            f"profile_{self._user_id}_*.json"
        )

        for path in glob.glob(pattern):
            try:
                os.remove(path)
                chain_logger.info(f"Deleted profile file: {path}")
            except OSError as e:
                chain_logger.error(f"Failed to delete {path}: {e}")
