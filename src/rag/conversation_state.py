import os, glob, json
from datetime import datetime

from ..config import config 
from ..utils.logging import get_logger 

from .conversation_analysis import *
from .utilclasses import ConversationState

logger = get_logger('chain.state_manager')

class ConversationStateManager:
    def __init__(self, user_id) -> None:
        self._user_id = user_id
        self.conversation_state: ConversationState = {
            'session_id': self._user_id,
            'user_id': self._user_id,
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
        }


    def update_conversation_state(self, user_query: str, agent_response: str) -> None:
        """Update conversation state by extracting information from the conversation."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        # Combine query and response for analysis
        conversation_text = f"{user_query} {agent_response}"

        # Extract profile information
        if not self.conversation_state.get('experience_years'):
            exp_years = extract_experience_years(conversation_text)
            if exp_years:
                self.conversation_state['experience_years'] = exp_years
                logger.info(f"Extracted experience years: {exp_years}")

        if not self.conversation_state.get('leadership_years'):
            lead_years = extract_leadership_years(conversation_text)
            if lead_years:
                self.conversation_state['leadership_years'] = lead_years
                logger.info(f"Extracted leadership years: {lead_years}")

        if not self.conversation_state.get('field'):
            field = extract_field(conversation_text)
            if field:
                self.conversation_state['field'] = field
                logger.info(f"Extracted field: {field}")

        if not self.conversation_state.get('interest'):
            interest = extract_interest(conversation_text)
            if interest:
                self.conversation_state['interest'] = interest
                logger.info(f"Extracted interest: {interest}")

        # Extract name
        if not self.conversation_state.get('user_name'):
            name = extract_name(conversation_text)
            if name:
                self.conversation_state['user_name'] = name
                logger.info(f"Extracted name: {name}")

        # Detect handover request from the user only; assistant soft offers should not count.
        if detect_handover_request(user_query):
            self.conversation_state['handover_requested'] = True
            logger.info("Handover request detected")

        # Check for program mentions
        programs = ['EMBA', 'IEMBA', 'EMBA X']
        for program in programs:
            if program.lower() in conversation_text.lower():
                if program not in self.conversation_state['program_interest']:
                    self.conversation_state['program_interest'].append(program)

        # Update suggested program
        suggested = determine_suggested_program(self.conversation_state)
        if suggested and not self.conversation_state.get('suggested_program'):
            self.conversation_state['suggested_program'] = suggested
            logger.info(f"Suggested program: {suggested}")


    def log_user_profile(self) -> None:
        """Log user profile to JSON file."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        try:
            # Create logs directory if it doesn't exist
            log_dir = os.path.join('logs', 'user_profiles')
            os.makedirs(log_dir, exist_ok=True)

            # Create profile data
            profile_data = {
                'session_id': self.conversation_state['session_id'],
                'user_id': self.conversation_state['user_id'],
                'name': self.conversation_state.get('user_name'),
                'timestamp': datetime.now().isoformat(),
                'experience_years': self.conversation_state.get('experience_years'),
                'leadership_years': self.conversation_state.get('leadership_years'),
                'field': self.conversation_state.get('field'),
                'interest': self.conversation_state.get('interest'),
                'suggested_program': self.conversation_state.get('suggested_program'),
                'handover': self.conversation_state.get('handover_requested'),
                'user_language': self.conversation_state.get('user_language'),
                'program_interest': self.conversation_state.get('program_interest', []),
            }

            # Log file path with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(log_dir, f'profile_{self._user_id}_{timestamp}.json')

            # Write to file
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, indent=2, ensure_ascii=False)

            logger.info(f"User profile logged to {log_file}")

        except Exception as e:
            logger.error(f"Failed to log user profile: {e}")
    
    def wipe_session_data(self) -> None:
        """Delete in-memory session data and on-disk profile files (GDPR withdrawal)."""

        # --- 1) In-memory wipe ---
        self._conversation_history = []
        self.conversation_state.update({
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

        # --- 2) On-disk wipe (delete profile_<user_id>_*.json) ---
        if not self._user_id:
            logger.warning("wipe_session_data called without user_id – skipping file deletion")
            return

        pattern = os.path.join(
            "logs",
            "user_profiles",
            f"profile_{self._user_id}_*.json"
        )

        for path in glob.glob(pattern):
            try:
                os.remove(path)
                logger.info(f"Deleted profile file: {path}")
            except OSError as e:
                logger.error(f"Failed to delete {path}: {e}")
