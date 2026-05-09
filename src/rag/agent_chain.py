from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from langchain.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain.agents.middleware import ModelFallbackMiddleware
from langchain.agents.structured_output import ProviderStrategy

import uuid
import json
import os
import re
import random
import glob
from datetime import datetime

from src.database.weavservice import WeaviateService

from src.rag.utilclasses import *
from src.const.agent_response_constants import *
from src.rag.middleware import (
    AgentChainMiddleware as chainmdw,
    ContextRetrievalError,
)
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf
from src.rag.input_handler import InputHandler
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian
# from src.rag.quality_score_handler import QualityEvaluationResult, QualityScoreHandler
from src.rag.language_detection import LanguageDetector

from src.utils.logging import get_logger
from src.utils.lang import get_language_name
from src.config import config

from ..cache.cache import Cache

chain_logger = get_logger('agent_chain')


class ExecutiveAgentChain:
    def __init__(self, language: str = 'en', session_id: str | None = None) -> None:
        self._initial_language  = language
        self._stored_language = language
        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agents()
        self._conversation_history = [] 
        self._pending_continuation: str | None = None
        self._programme_overview_detail_level = 0
        self._cache = Cache.get_cache()

        # Confidence scoring is intentionally disabled here because the extra
        # model call adds latency and has not been reliable enough to justify it.
        # if config.chain.EVALUATE_RESPONSE_QUALITY:
        #     self._quality_handler = QualityScoreHandler()
        self._language_detector = LanguageDetector()

        # Generate unique user ID for this session
        self._user_id = session_id or str(uuid.uuid4())

        # Initialize conversation state with user profile tracking
        self._conversation_state: ConversationState = {
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

        # Track scope violations for escalation
        self._scope_violation_counts: dict[str, int] = {}
        self._aggressive_violation_count = 0

        chain_logger.info(f"Initialized new Agent Chain for language '{language}' with user_id: {self._user_id}")

    @staticmethod
    def _subagent_retrieval_fallback(program: str) -> str:
        fallback_by_program = {
            'emba': (
                "Die Kontextdatenbank ist momentan nicht verfuegbar, daher kann ich keine "
                "aktuellen Rankings oder Alumni-Fakten nachladen. Verlaesslich fest hinterlegt "
                "sind fuer den **EMBA HSG**: deutschsprachig, berufsbegleitend, **18 Monate** "
                "(verlaengerbar bis 48 Monate), Start **14. September 2026**, "
                "**CHF 77'500** Studiengebuehren und ein klarer Fokus auf General Management, "
                "Leadership und den DACH-Raum."
            ),
            'iemba': (
                "Die Kontextdatenbank ist momentan nicht verfuegbar, daher kann ich keine "
                "aktuellen Rankings oder Alumni-Fakten nachladen. Verlaesslich fest hinterlegt "
                "sind fuer den **IEMBA HSG**: englischsprachig, berufsbegleitend, "
                "**18 Monate**, Start **24. August 2026**, internationaler Fokus und "
                "**CHF 85'000** Studiengebuehren."
            ),
            'embax': (
                "Die Kontextdatenbank ist momentan nicht verfuegbar, daher kann ich keine "
                "aktuellen Rankings oder Alumni-Fakten nachladen. Verlaesslich fest hinterlegt "
                "sind fuer **emba X**: englischsprachig, berufsbegleitend, Fokus auf Business, "
                "Technologie und Transformation, Start **31. August 2026** und "
                "Studiengebuehren von **CHF 99'000** bis zur ersten Bewerbungsfrist "
                "beziehungsweise **CHF 110'000** bis zur finalen Frist."
            ),
        }
        return fallback_by_program[program]

    def _retrieve_context(self, query: str, program: str, language: str = None):
        """
        Send the query to the vector database to retrieve additional information about the program.

        Args:
            query: Keywords depicting information you want to retrieve in the primary language.
            program: Name of the program (either 'emba', 'iemba' or 'emba x') for which the information is requested.
            language: Optional parameter (either 'en' for English language or 'de' for German language). This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language. Use this parameter only if there's not enough information in your main language.
        """
        lang = language if language in ['en', 'de'] else self._initial_language
        try:
            response, _ = self._dbservice.query(
                query=query,
                lang=lang,
                limit=config.get('TOP_K_RETRIEVAL'),
                property_filters={
                    'programs': [program],
                },
            )
            serialized = '\n\n'.join([doc.properties.get('body', '') for doc in response.objects])
            return serialized
        except Exception as e:
            raise e

    def _call_emba_agent(self, query: str) -> str:
        """
        Invokes the EMBA support agent to retrieve more detailed information about the EMBA program.
        
        Args:
            query: Query to the EMBA support agent. Provide collected user data in the query if possible.
        """
        try:
            structured_response = self._query(
                agent=self._agents['emba'],
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return structured_response.response
        except ContextRetrievalError as e:
            chain_logger.error(f"EMBA retrieval error: {e}")
            return self._subagent_retrieval_fallback('emba')
        except Exception as e:
            chain_logger.error(f"EMBA Agent error: {e}")
            raise RuntimeError("Unable to retrieve EMBA information at this time.")

    def _call_iemba_agent(self, query: str) -> str:
        """
        Invokes the IEMBA support agent to retrieve more detailed information about the IEMBA program.
        
        Args:
            query: Query to the IEMBA support agent. Provide collected user data in the query if possible.
        """
        try:
            structured_response = self._query(
                agent=self._agents['iemba'],
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return structured_response.response
        except ContextRetrievalError as e:
            chain_logger.error(f"IEMBA retrieval error: {e}")
            return self._subagent_retrieval_fallback('iemba')
        except Exception as e:
            chain_logger.error(f"IEMBA Agent error: {e}")
            raise RuntimeError("Unable to retrieve IEMBA information at this time.")

    def _call_embax_agent(self, query: str) -> str:
        """
        Invokes the emba X support agent to retrieve more detailed information about the emba X program.
        
        Args:
            query: Query to the emba X support agent. Provide collected user data in the query if possible.
        """
        try:
            structured_response = self._query(
                agent=self._agents['embax'],
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return structured_response.response
        except ContextRetrievalError as e:
            chain_logger.error(f"emba X retrieval error: {e}")
            return self._subagent_retrieval_fallback('embax')
        except Exception as e:
            chain_logger.error(f"emba X Agent error: {e}")
            raise RuntimeError("Unable to retrieve emba X information at this time.")

    def _init_agents(self):
        config: RunnableConfig = {
            'configurable': {'thread_id': 0}
        }
        fallback_middleware = ModelFallbackMiddleware(
            *modelconf.get_fallback_models()
        )
        tool_retrieve_context = tool(
            name_or_callable='retrieve_context',
            runnable=self._retrieve_context,
            return_direct=False,
            parse_docstring=True,
        )
        tools_agent_calling = [
            tool(
                name_or_callable='call_emba_agent',
                runnable=self._call_emba_agent,
                return_direct=False,
                parse_docstring=True,
            ),
            tool(
                name_or_callable='call_iemba_agent',
                runnable=self._call_iemba_agent,
                return_direct=False,
                parse_docstring=True,
            ),
            tool(
                name_or_callable='call_embax_agent',
                runnable=self._call_embax_agent,
                return_direct=False,
                parse_docstring=True,
            ),
        ]
        agents = {
            'lead': create_agent(
                name="lead_agent",
                model=modelconf.get_main_agent_model(),
                tools=tools_agent_calling,
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt('lead', language=self._initial_language),
                middleware=[
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                    fallback_middleware,
                ],
                context_schema=AgentContext,
                response_format=ProviderStrategy(
                    StructuredAgentResponse
                ),
            ),
        }
        for agent in ['emba', 'iemba', 'embax']:
            agents[agent] = create_agent(
                name=f"{agent}_agent",
                model=modelconf.get_subagent_model(),
                tools=[tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(agent, language=self._initial_language),
                middleware=[
                    fallback_middleware,
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                ],
                context_schema=AgentContext,
            )
        return agents, config

    def _extract_experience_years(self, conversation: str) -> int | None:
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

    def _extract_leadership_years(self, conversation: str) -> int | None:
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

    def _previous_response_offered_booking(self) -> bool:
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

        for message in reversed(self._conversation_history):
            if not isinstance(message, AIMessage):
                continue
            content = getattr(message, "content", "") or getattr(message, "text", "")
            if isinstance(content, list):
                content = " ".join(str(part) for part in content)
            content_lower = str(content).lower()
            return any(term in content_lower for term in booking_offer_terms)

        return False

    def _get_latest_ai_message_content(self, skip_latest: bool = False) -> str:
        """Return the latest assistant message content from conversation history."""
        ai_messages_seen = 0

        for message in reversed(self._conversation_history):
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

    def _is_booking_preference_follow_up(self, query: str) -> bool:
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

    def _previous_response_requested_booking_preferences(self) -> bool:
        """Return True when the previous assistant turn asked clarifying booking questions."""
        content_lower = self._get_latest_ai_message_content().lower()
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

    def _response_commits_to_showing_booking_widget(self, response: str) -> bool:
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
    def _is_explicit_booking_intent(self, query: str) -> bool:
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
            self._previous_response_offered_booking()
            and any(contains_term(term) for term in acceptance_terms)
        )

    def _determine_suggested_program(self) -> str | None:
        """Determine recommended program based on user profile."""
        state = self._conversation_state

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

    def _update_conversation_state(self, user_query: str, agent_response: str) -> None:
        """Update conversation state by extracting information from the conversation."""
        if not config.convstate.TRACK_USER_PROFILE:
            return

        # Combine query and response for analysis
        conversation_text = f"{user_query} {agent_response}"

        # Extract profile information
        if not self._conversation_state.get('experience_years'):
            exp_years = self._extract_experience_years(conversation_text)
            if exp_years:
                self._conversation_state['experience_years'] = exp_years
                chain_logger.info(f"Extracted experience years: {exp_years}")

        if not self._conversation_state.get('leadership_years'):
            lead_years = self._extract_leadership_years(conversation_text)
            if lead_years:
                self._conversation_state['leadership_years'] = lead_years
                chain_logger.info(f"Extracted leadership years: {lead_years}")

        if not self._conversation_state.get('field'):
            field = self._extract_field(conversation_text)
            if field:
                self._conversation_state['field'] = field
                chain_logger.info(f"Extracted field: {field}")

        if not self._conversation_state.get('interest'):
            interest = self._extract_interest(conversation_text)
            if interest:
                self._conversation_state['interest'] = interest
                chain_logger.info(f"Extracted interest: {interest}")

        # Extract name
        if not self._conversation_state.get('user_name'):
            name = self._extract_name(conversation_text)
            if name:
                self._conversation_state['user_name'] = name
                chain_logger.info(f"Extracted name: {name}")

        # Detect handover request from the user only; assistant soft offers should not count.
        if self._detect_handover_request(user_query):
            self._conversation_state['handover_requested'] = True
            chain_logger.info("Handover request detected")

        # Check for program mentions
        programs = ['EMBA', 'IEMBA', 'EMBA X']
        for program in programs:
            if program.lower() in conversation_text.lower():
                if program not in self._conversation_state['program_interest']:
                    self._conversation_state['program_interest'].append(program)

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
    
    def wipe_session_data(self) -> None:
        """Delete in-memory session data and on-disk profile files (GDPR withdrawal)."""

        # --- 1) In-memory wipe ---
        self._conversation_history = []
        self._pending_continuation = None
        self._programme_overview_detail_level = 0
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
        self._scope_violation_counts = {}
        self._aggressive_violation_count = 0

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

    def generate_greeting(self) -> str:
        greeting_message = random.choice(GREETING_MESSAGES[self._stored_language])
        return greeting_message

    @traceable
    def query(self, query: str) -> LeadAgentQueryResponse:
        """
        Phase 1: Validation, Scope-Check and language detection.
        Does not call the agent directly.
        """
        # Remember fallback language
        current_language = self._stored_language 

        if len(self._conversation_history) >= config.convstate.MAX_CONVERSATION_TURNS:
            return LeadAgentQueryResponse(
                response = CONVERSATION_END_MESSAGE[current_language],
                language = current_language,
                max_turns_reached = True,
                relevant_programs=[],
                processed_query = query
            ) 

        # 2. Input Processing
        processed_query, is_valid = InputHandler.process_input(
            query,
            [msg for msg in self._conversation_history if isinstance(msg, (HumanMessage, AIMessage))]
        )

        if not is_valid or not processed_query:
            chain_logger.warning(f"Invalid input received: '{query}'")
            return LeadAgentQueryResponse(
                response=NOT_VALID_QUERY_MESSAGE[self._stored_language],
                language=current_language,
                processed_query=query
            )

        # Log check
        if processed_query != query:
            chain_logger.info(f"Interpreted input '{query}' as '{processed_query}'")

        # 3. Language Detection
        # First: Check for explicit language switch request (overrides lock)
        explicit_switch = self._language_detector.detect_explicit_switch_request(processed_query)
        if explicit_switch:
            self._stored_language = explicit_switch
            current_language = explicit_switch
            self._conversation_state['user_language'] = explicit_switch
        elif self._language_detector.is_language_neutral_program_reference(processed_query):
            chain_logger.info(
                f"Skipping language re-detection for language-neutral programme reference: '{processed_query}'"
            )
            current_language = self._stored_language
        else:
            # Count user messages in conversation history
            user_message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])

            # Lock language after N user messages (allows language switch early in conversation)
            lang_lock_n = config.convstate.LOCK_LANGUAGE_AFTER_N_MESSAGES
            if lang_lock_n > 0 and user_message_count >= lang_lock_n:
                chain_logger.info(f"Language locked to '{self._stored_language}' (after {user_message_count} messages)")
                current_language = self._stored_language
            else:
                detected_language = self._language_detector.detect_language(processed_query)
                self._conversation_state['user_language'] = detected_language

                # Language validation
                if detected_language in ['de', 'en']:
                    self._stored_language = detected_language
                    current_language = detected_language
                else:
                    chain_logger.info("Invalid language detected.")
                    return LeadAgentQueryResponse(
                        response=LANGUAGE_FALLBACK_MESSAGE[current_language],
                        language=current_language,
                        processed_query=processed_query
                    )

        if (
            self._is_continuation_request(processed_query)
            and self._latest_ai_mentions_multiple_programmes()
        ):
            return self._serve_programme_overview(
                processed_query=processed_query,
                response_language=current_language,
                detailed=True,
            )

        if (
            self._latest_ai_mentions_multiple_programmes()
            and self._is_profile_context_update(processed_query)
            and not self._query_mentions_specific_programme(processed_query)
        ):
            return self._serve_programme_overview(
                processed_query=processed_query,
                response_language=current_language,
                detailed=False,
            )

        if self._pending_continuation and self._is_continuation_request(processed_query):
            return self._serve_pending_continuation(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._pending_continuation:
            chain_logger.info("Discarding pending continuation because the user started a new request.")
            self._pending_continuation = None

        # 4. Scope Check
        scope_type = ScopeGuardian.check_scope(processed_query, current_language)

        if scope_type != 'on_topic':
            chain_logger.info(f"Out-of-scope query detected: {scope_type}")
            if scope_type == 'aggressive':
                self._aggressive_violation_count += 1
                attempt_count = self._aggressive_violation_count
            else:
                self._scope_violation_counts[scope_type] = self._scope_violation_counts.get(scope_type, 0) + 1
                attempt_count = self._scope_violation_counts[scope_type]

            should_escalate, escalation_type = ScopeGuardian.should_escalate(
                processed_query, scope_type, attempt_count
            )

            if should_escalate:
                redirect_msg = ScopeGuardian.get_escalation_message(escalation_type, current_language)
            else:
                redirect_msg = ScopeGuardian.get_redirect_message(scope_type, current_language)

            self._conversation_history.append(HumanMessage(processed_query))
            self._conversation_history.append(AIMessage(redirect_msg))

            return LeadAgentQueryResponse(
                response=redirect_msg,
                language=current_language,
                processed_query=processed_query,
                appointment_requested=False,
                show_booking_widget=False,
            )

        if self._is_general_mba_overview_request(processed_query):
            return self._serve_programme_overview(
                processed_query=processed_query,
                response_language=current_language,
                detailed=False,
            )
        
        # 5. Check if cached data already exists for this session 
        if config.cache.ENABLED:
            cached_data = self._cache.get(query, current_language, self._user_id)
            if cached_data and isinstance(cached_data, dict):
                return LeadAgentQueryResponse(
                    response=cached_data["response"],
                    language=current_language,
                    appointment_requested=cached_data.get("appointment_requested", False),
                    show_booking_widget=cached_data.get("show_booking_widget", False),
                    relevant_programs=cached_data.get("relevant_programs", []),
                )
            

        # 6. Preprocessing is finished - the agent has to answer the query 
        response = self._query_lead(query) 
        
        if config.cache.ENABLED and response.should_cache:
            self._cache.set(
                key=query,
                value={
                    "response":              response.response,
                    "appointment_requested": response.appointment_requested,
                    "show_booking_widget":    response.show_booking_widget,
                    "relevant_programs":     response.relevant_programs,
                },
                language   = current_language,
                session_id = self._user_id,
            )
        
        return response 


    def _query_lead(self, preprocessed_query: str) -> LeadAgentQueryResponse:
        """
        Phase 2: Execute agent.
        Takes the ALREADY validated query from the preprocessing phase.
        """
        # Reset scope-violation tracking
        self._scope_violation_counts = {}
        
        response_language = self._stored_language
        explicit_booking_intent = self._is_explicit_booking_intent(preprocessed_query)
        booking_preference_follow_up = (
            self._conversation_state.get('handover_requested') is True
            and self._previous_response_requested_booking_preferences()
            and self._is_booking_preference_follow_up(preprocessed_query)
        )
       
        # 1. History Update 
        self._conversation_history.append(HumanMessage(preprocessed_query))

        # 2. System instruction
        language_instruction = SystemMessage(f"Respond in {get_language_name(response_language)} language.")

        # 3. Agent Call
        structured_response = self._query(
            agent=self._agents['lead'],
            messages=self._conversation_history + [language_instruction], 
        )
        agent_response = structured_response.response
        chain_logger.info(f"Is answer context dependent: {structured_response.is_context_dependent}")
        chain_logger.info(f"Appointment Requested: {structured_response.appointment_requested}")
        chain_logger.info(f"Show Booking Widget: {structured_response.show_booking_widget}")
        chain_logger.info(f"Relevant Programs: {structured_response.relevant_programs}")

        # Keep the complete answer in internal memory even when the UI only
        # shows the first chunk. Otherwise follow-up turns only "remember" the
        # truncated version and tend to repeat themselves.
        full_response = ResponseFormatter.clean_response(
            ResponseFormatter.remove_tables(agent_response)
        )

        # 4. Formatting
        if (
            config.chain.ENABLE_RESPONSE_CHUNKING
            and not self._text_mentions_multiple_programmes(full_response)
        ):
            formatted_response, continuation = ResponseFormatter.chunk_response(
                full_response,
                config.chain.MAX_RESPONSE_WORDS_LEAD,
                response_language,
            )
            self._pending_continuation = continuation
        else:
            formatted_response = full_response
            self._pending_continuation = None

        formatted_response = ResponseFormatter.clean_response(formatted_response)

        confidence_fallback = False
        # if config.chain.EVALUATE_RESPONSE_QUALITY:
        #     quality_evaluation: QualityEvaluationResult = self._quality_handler. \
        #         evaluate_response_quality(preprocessed_query, formatted_response)
        #
        #     chain_logger.info(f"Quality Score: {quality_evaluation.overall_score:1.2f}")
        #
        #     if quality_evaluation.overall_score < config.chain.CONFIDENCE_THRESHOLD:
        #         confidence_fallback = True
        #         formatted_response = CONFIDENCE_FALLBACK_MESSAGE[response_language]
        #         chain_logger.info("Fallback Mechanism activated!")

        history_response = ResponseFormatter.format_name_of_university(
            full_response,
            language=response_language,
        )

        # Add the full answer to internal history, not the visible chunk.
        self._conversation_history.append(AIMessage(history_response))

        # 6. Profiling
        if config.convstate.TRACK_USER_PROFILE:
            self._update_conversation_state(preprocessed_query, history_response)
            
            message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])
            if message_count % 5 == 0 or self._conversation_state.get('suggested_program'):
                self._log_user_profile()

        formatted_response = ResponseFormatter.format_name_of_university(
            formatted_response,
            language=response_language,
        )

        # Proactive booking offer.
        # When the lead model signals booking readiness AND the assessment chain
        # has identified a clear programme match, the booking widget is shown
        # without waiting for an explicit "book"/"appointment" word from the user.
        # The match comes from the existing profile-based assessment
        # (suggested_program, set by _update_conversation_state above) or from
        # relevant_programs returned by the lead model. Without this gate, the
        # earlier user-led-only logic meant the widget effectively never fired.
        clear_programme_match = (
            self._conversation_state.get('suggested_program') is not None
            or bool(structured_response.relevant_programs)
        )
        proactive_booking_offer = (
            clear_programme_match
            and structured_response.show_booking_widget
        )

        booking_flow_requested = (
            explicit_booking_intent
            or booking_preference_follow_up
            or proactive_booking_offer
        )
        appointment_requested = bool(booking_flow_requested)
        show_booking_widget = bool(
            booking_flow_requested and (
                structured_response.show_booking_widget
                or self._response_commits_to_showing_booking_widget(formatted_response)
            )
        )

        if proactive_booking_offer and not (explicit_booking_intent or booking_preference_follow_up):
            chain_logger.info(
                "Proactive booking offer triggered "
                f"(suggested_program={self._conversation_state.get('suggested_program')}, "
                f"relevant_programs={structured_response.relevant_programs})"
            )
        elif structured_response.appointment_requested and not booking_flow_requested:
            chain_logger.info("Suppressed booking state because no programme match or booking intent was detected.")
        elif booking_preference_follow_up and show_booking_widget:
            chain_logger.info("Continuing active booking flow and showing booking widget for a preference follow-up.")
        
        return LeadAgentQueryResponse(
            response = formatted_response,
            language = response_language,
            confidence_fallback = confidence_fallback,
            should_cache = False if (confidence_fallback or appointment_requested or structured_response.is_context_dependent) else True,
            processed_query = preprocessed_query,
            appointment_requested = appointment_requested,
            show_booking_widget = show_booking_widget,
            relevant_programs = structured_response.relevant_programs
        )

    def _is_continuation_request(self, query: str) -> bool:
        normalized = re.sub(r"[.!?,;:]", " ", query.lower()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        continuation_terms = {
            "ja",
            "ja bitte",
            "bitte",
            "gerne",
            "weiter",
            "bitte weiter",
            "mehr",
            "mehr details",
            "mehr details bitte",
            "ja mehr details",
            "noch mehr",
            "fortfahren",
            "weiter bitte",
            "and",
            "and more",
            "continue",
            "continue please",
            "more",
            "more details",
            "more details please",
        }
        return normalized in continuation_terms

    def _query_mentions_specific_programme(self, query: str) -> bool:
        query_lower = query.lower()
        return any(
            term in query_lower
            for term in [
                "emba hsg",
                "international emba",
                "iemba",
                "emba x",
                "embax",
            ]
        )

    def _is_general_mba_overview_request(self, query: str) -> bool:
        query_lower = query.lower()
        if self._query_mentions_specific_programme(query_lower):
            return False

        general_mba_terms = [
            "mba",
            "executive mba",
            "weiterbildungs-mba",
            "weiterbildungsmba",
        ]
        discovery_terms = [
            "interessiere",
            "interested",
            "welche",
            "which",
            "option",
            "programm",
            "program",
            "passt",
            "fit",
            "geeignet",
            "empfehlen",
            "recommend",
        ]
        return (
            any(term in query_lower for term in general_mba_terms)
            and any(term in query_lower for term in discovery_terms)
        )

    def _is_profile_context_update(self, query: str) -> bool:
        query_lower = query.lower()
        profile_terms = [
            "jahre",
            "years",
            "chefarzt",
            "chief physician",
            "arzt",
            "doctor",
            "leadership",
            "führung",
            "fuehrung",
            "leiter",
            "leitung",
            "manager",
            "experience",
            "erfahrung",
            "berufserfahrung",
        ]
        return any(term in query_lower for term in profile_terms)

    def _text_mentions_multiple_programmes(self, text: str) -> bool:
        text_lower = text.lower()
        if not text_lower:
            return False

        programme_mentions = [
            "emba hsg" in text_lower or "deutschsprachig" in text_lower,
            "iemba" in text_lower or "international emba" in text_lower,
            "emba x" in text_lower or "embax" in text_lower,
        ]
        return sum(programme_mentions) >= 2

    def _latest_ai_mentions_multiple_programmes(self) -> bool:
        return self._text_mentions_multiple_programmes(
            self._get_latest_ai_message_content()
        )

    def _build_programme_overview_response(self, language: str, detailed: bool) -> str:
        if language == 'en':
            if not detailed:
                return (
                    "Your profile mainly clarifies the admissions level: with substantial medical leadership experience, "
                    "the Executive MBA options are broadly plausible. The programme choice should now be based on goals, "
                    "not on an automatic classification.\n\n"
                    "1. **EMBA HSG**: German-speaking, DACH-focused general management programme. It is part-time, "
                    "**18 months** long, extendable up to **48 months**, with **9 core courses**, **5 electives**, "
                    "about **14 campus weeks**, a capstone project, and **CHF 77,500** tuition. It fits leaders who "
                    "want stronger strategy, finance, organisation, and leadership capability in the German-speaking market.\n\n"
                    "2. **IEMBA HSG**: English-speaking international Executive MBA. It is part-time, **18 months** long, "
                    "with **10 core courses**, **4 electives**, **10 campus weeks**, **4 weeks abroad**, a thesis, and "
                    "**CHF 85,000** tuition. It fits leaders who want global exposure, international peer learning, and "
                    "management confidence beyond one national healthcare system.\n\n"
                    "3. **emba X**: English-speaking joint degree from **ETH Zurich** and the **University of St.Gallen**. "
                    "It is part-time, **18 months**, blended across Zurich and St.Gallen, with a strong focus on business, "
                    "technology, innovation, transformation, and **CHF 99,000 / CHF 110,000** tuition depending on the "
                    "application deadline. It fits leaders driving digital transformation, MedTech, Health-IT, or innovation."
                )

            if self._programme_overview_detail_level <= 1:
                return (
                    "More detail across all three programmes:\n\n"
                    "**EMBA HSG** aims to strengthen broad general-management judgement for leaders in the DACH context. "
                    "For a hospital leader, the practical value is strategy, finance, governance, organisation design, "
                    "negotiation, and change leadership in German-speaking healthcare organisations. The capstone project "
                    "can be tied to a real clinic or hospital transformation topic.\n\n"
                    "**IEMBA HSG** aims to build international management perspective. The value is not only the English "
                    "language; it is the global cohort and modules across different regions. For healthcare leadership, "
                    "that is useful when you work with international partners, global health organisations, industry, "
                    "research networks, or cross-border clinical initiatives.\n\n"
                    "**emba X** aims at leadership where business and technology meet. It is the most relevant option if "
                    "your goals include digital transformation, MedTech, Health-IT, AI-enabled processes, innovation, or "
                    "large organisational change. Its distinctive feature is the integrated **ETH Zurich** plus "
                    "**University of St.Gallen** joint-degree setting and access to both alumni networks."
                )

            return (
                "The next useful distinction is by goals and working context:\n\n"
                "- Choose **EMBA HSG** if your main goal is stronger economic and organisational steering of a hospital "
                "in the DACH environment: budgeting, governance, leadership, negotiation, and operational change.\n"
                "- Choose **IEMBA HSG** if your main goal is international exposure: learning with a global cohort, "
                "working across health systems, and building confidence for international partnerships or organisations.\n"
                "- Choose **emba X** if your main goal is transformation through technology: digital care pathways, "
                "MedTech collaboration, innovation portfolios, data/AI initiatives, or culture change around new tools.\n\n"
                "For a senior medical leadership role, all three can be plausible. The deciding factor is whether your next "
                "development goal is DACH management depth, international management breadth, or technology-led transformation."
            )

        if not detailed:
            return (
                "Das Profil klärt vor allem die Zulassungsebene: Mit langjähriger ärztlicher Führungsverantwortung sind "
                "die Executive-MBA-Optionen grundsätzlich plausibel. Die Programmwahl sollte jetzt über Ihre Ziele laufen, "
                "nicht über eine automatische Einordnung.\n\n"
                "1. **EMBA HSG**: deutschsprachig, DACH-Fokus, General Management und Leadership. Das Programm ist "
                "berufsbegleitend, dauert **18 Monate** und kann auf **48 Monate** verlängert werden. Es umfasst "
                "**9 Kernkurse**, **5 Wahlfächer**, rund **14 Präsenzwochen** und ein Capstone-Projekt. Studiengebühr: "
                "**CHF 77'500**. Ziel: Management-, Finanz-, Strategie- und Führungskompetenz im deutschsprachigen Kontext stärken.\n\n"
                "2. **IEMBA HSG**: englischsprachig, international ausgerichtet. Das Programm ist berufsbegleitend, "
                "**18 Monate** lang, mit **10 Kernkursen**, **4 Wahlkursen**, **10 Präsenzwochen**, **4 Wochen Auslandsmodule** "
                "und Thesis. Studiengebühr: **CHF 85'000**. Ziel: internationale Managementperspektive, globale Peer Group "
                "und Führung über verschiedene Märkte und Systeme hinweg.\n\n"
                "3. **emba X**: englischsprachiges Joint Degree von **ETH Zürich** und **Universität St.Gallen**. "
                "Berufsbegleitend, **18 Monate**, blended in Zürich und St.Gallen, mit Fokus auf Business, Technologie, "
                "Innovation und Transformation. Studiengebühr: **CHF 99'000 / CHF 110'000** je nach Bewerbungsfrist. "
                "Ziel: Führung an der Schnittstelle von Management, Technologie und Veränderung."
            )

        if self._programme_overview_detail_level <= 1:
            return (
                "Weitere Details zu **allen drei Programmen**, ohne Sie vorschnell auf eines festzulegen:\n\n"
                "**EMBA HSG** zielt auf breite General-Management-Kompetenz im DACH-Raum. Für eine Chefarzt-Rolle ist das "
                "relevant, wenn Sie Strategie, Finanzen, Governance, Organisation, Verhandlung und Change Management in "
                "einer Klinik oder einem Spital stärken wollen. Das Capstone-Projekt kann direkt auf ein reales "
                "Klinikthema ausgerichtet werden, etwa Prozessoptimierung, Ressourcensteuerung oder Organisationsentwicklung.\n\n"
                "**IEMBA HSG** zielt auf internationale Managementkompetenz. Der Mehrwert liegt in der englischsprachigen "
                "globalen Kohorte und den internationalen Modulen. Für das Gesundheitswesen ist das besonders sinnvoll, "
                "wenn Sie mit internationalen Partnern, globalen Gesundheitsorganisationen, Industrie, Forschung oder "
                "grenzüberschreitenden Versorgungsfragen arbeiten.\n\n"
                "**emba X** zielt auf Führung an der Schnittstelle von Business und Technologie. Das ist besonders relevant, "
                "wenn Ihre Ziele Digitalisierung, MedTech, Health-IT, datengetriebene Prozesse, Innovation oder grosse "
                "Transformationsprojekte im Spital betreffen. Der besondere Punkt ist die Kombination aus **ETH Zürich** "
                "und **Universität St.Gallen** sowie der Zugang zu beiden Netzwerken."
            )

        return (
            "Die nächste sinnvolle Unterscheidung läuft über Ziele und Arbeitskontext:\n\n"
            "- **EMBA HSG** passt am besten, wenn Sie Ihre ökonomische, organisatorische und strategische Steuerung im "
            "deutschsprachigen Spitalumfeld vertiefen wollen: Budget, Governance, Personalführung, Verhandlung, Change.\n"
            "- **IEMBA HSG** passt am besten, wenn Sie internationaler arbeiten möchten: Vergleich von Märkten und "
            "Organisationen, globale Peer Group, internationale Kooperationen, Industrie- oder Forschungspartner.\n"
            "- **emba X** passt am besten, wenn Technologie und Transformation im Zentrum stehen: digitale Patientenpfade, "
            "MedTech, Health-IT, Daten-/AI-Projekte, Innovationsportfolios oder kultureller Wandel im Spital.\n\n"
            "Für eine Chefarzt-Rolle sind alle drei plausibel. Ausschlaggebend ist, ob Ihr nächster Entwicklungsschwerpunkt "
            "DACH-Management, Internationalität oder technologiegetriebene Transformation ist."
        )

    def _serve_programme_overview(
        self,
        processed_query: str,
        response_language: str,
        detailed: bool,
    ) -> LeadAgentQueryResponse:
        chain_logger.info("Serving deterministic three-programme overview without a model call.")
        response = self._build_programme_overview_response(response_language, detailed=detailed)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._programme_overview_detail_level = (
            max(2, self._programme_overview_detail_level + 1)
            if detailed
            else 1
        )
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=["emba", "iemba", "emba_x"],
        )

    def _serve_pending_continuation(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        chain_logger.info("Serving pending continuation without a new model call.")

        formatted_response, continuation = ResponseFormatter.chunk_response(
            self._pending_continuation or "",
            config.chain.MAX_RESPONSE_WORDS_LEAD,
            response_language,
        )
        self._pending_continuation = continuation
        formatted_response = ResponseFormatter.clean_response(formatted_response)
        formatted_response = ResponseFormatter.format_name_of_university(
            formatted_response,
            language=response_language,
        )

        return LeadAgentQueryResponse(
            response=formatted_response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=[],
        )

    def _query(self, agent, messages: list, thread_id: str = None) -> StructuredAgentResponse:
        try:
            config = self._config.copy()
            config['configurable']['thread_id'] = thread_id or 0

            result: AIMessage = agent.invoke(
                {"messages": messages},
                config=config,
                context=AgentContext(agent_name=agent.name),
            )
            response = result.get(
                'structured_response',
                StructuredAgentResponse(
                    response=result['messages'][-1].text,
                )
            )
            return response
        except Exception as e:
            error_msg = e.body['message'] if hasattr(e, 'body') else str(e)
            chain_logger.error(f"Failed to invoke the agent: {error_msg}")
            return StructuredAgentResponse(
                response=QUERY_EXCEPTION_MESSAGE[self._stored_language],
            )
