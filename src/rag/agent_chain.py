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
        self._programme_overview_profile_context = False
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
            return self._normalise_programme_id(state['program_interest'][0])

        # Make recommendation based on profile
        experience = state.get('experience_years', 0) or 0
        leadership = state.get('leadership_years', 0) or 0

        if state.get('interest') and any(kw in state.get('interest', '').lower()
                                         for kw in ['digital', 'digitalisierung', 'innovation', 'technology', 'technologie']):
            return 'emba_x'

        # EMBA: 5+ years experience, 2+ years leadership
        if experience >= 5 and leadership >= 2:
            return 'emba'
        # IEMBA: International focus, 3+ years experience
        elif experience >= 3:
            return 'iemba'

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
        self._scope_violation_counts = {}
        self._aggressive_violation_count = 0

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
                profile_context=getattr(self, "_programme_overview_profile_context", False),
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
                profile_context=True,
            )

        preferred_programme = self._extract_programme_preference(processed_query)
        if preferred_programme and self._latest_ai_mentions_multiple_programmes():
            return self._serve_programme_next_steps(
                processed_query=processed_query,
                response_language=current_language,
                programme=preferred_programme,
            )

        if (
            self._previous_response_was_application_next_step()
            and self._is_application_process_detail_request(processed_query)
        ):
            application_programmes = self._resolve_known_application_programmes(processed_query)
            if application_programmes:
                return self._serve_application_process_details(
                    processed_query=processed_query,
                    response_language=current_language,
                    programmes=application_programmes,
                )

        application_programmes = self._resolve_application_programmes(processed_query)
        if application_programmes:
            return self._serve_application_next_steps(
                processed_query=processed_query,
                response_language=current_language,
                programmes=application_programmes,
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
                profile_context=False,
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

    def _extract_programme_preference(self, query: str) -> str | None:
        query_lower = query.lower()
        preference_terms = [
            "besser",
            "besserer fit",
            "beste",
            "am besten",
            "passt",
            "passender",
            "interessanter",
            "favorisiere",
            "tendiere",
            "klingt gut",
            "klingt besser",
            "finde ich gut",
            "finde ich besser",
            "nehme",
            "wähle",
            "waehle",
            "will",
            "möchte",
            "moechte",
            "sounds better",
            "best",
            "better fit",
            "prefer",
            "lean toward",
            "interested in",
            "i want",
            "i would choose",
        ]
        if not any(term in query_lower for term in preference_terms):
            return None

        if "emba x" in query_lower or "embax" in query_lower:
            return "emba_x"
        if "iemba" in query_lower or "international emba" in query_lower:
            return "iemba"
        if "emba hsg" in query_lower or re.search(r"\bemba\b", query_lower):
            return "emba"

        return None

    def _extract_programme_from_text(self, text: str) -> str | None:
        text_lower = text.lower()
        if "emba x" in text_lower or "embax" in text_lower:
            return "emba_x"
        if "iemba" in text_lower or "international emba" in text_lower:
            return "iemba"
        if "emba hsg" in text_lower:
            return "emba"
        return None

    def _extract_programmes_from_text(self, text: str) -> list[str]:
        text_lower = text.lower()
        programmes: list[str] = []

        if "emba x" in text_lower or "embax" in text_lower:
            programmes.append("emba_x")
        if "iemba" in text_lower or "international emba" in text_lower:
            programmes.append("iemba")
        if "emba hsg" in text_lower or re.search(r"\bgerman(?:-speaking)?\s+emba\b", text_lower):
            programmes.append("emba")

        return programmes

    @staticmethod
    def _normalise_programme_id(programme: str | None) -> str | None:
        if not programme:
            return None
        programme_lower = str(programme).lower().replace("-", "_").replace(" ", "_")
        if programme_lower in {"emba_x", "embax"}:
            return "emba_x"
        if programme_lower in {"iemba", "iemba_hsg", "international_emba"}:
            return "iemba"
        if programme_lower in {"emba", "emba_hsg"}:
            return "emba"
        return None

    def _is_application_next_step_request(self, query: str) -> bool:
        query_lower = query.lower()
        application_terms = [
            "bewerb",
            "bewerbung",
            "bewerben",
            "bewerbungsprozess",
            "bewerbungsunterlagen",
            "zulassung",
            "assessment",
            "application",
            "apply",
            "admission",
            "admissions",
            "admissions process",
            "application documents",
        ]
        return any(term in query_lower for term in application_terms)

    def _is_application_process_detail_request(self, query: str) -> bool:
        query_lower = query.lower()
        detail_terms = [
            "prozess",
            "ablauf",
            "schritt",
            "schritte",
            "unterlagen",
            "dokument",
            "dokumente",
            "fristen",
            "frist",
            "deadline",
            "deadlines",
            "timeline",
            "process",
            "steps",
            "documents",
            "wie läuft",
            "wie laeuft",
            "how does it work",
            "how does the process work",
        ]
        return any(term in query_lower for term in detail_terms)

    def _previous_response_was_application_next_step(self) -> bool:
        content_lower = self._get_latest_ai_message_content().lower()
        if not content_lower:
            return False

        application_terms = [
            "bewerbung zum",
            "bewerbungsschritt",
            "zulassungs- und beratungsgespräch",
            "terminoptionen und kontaktdaten",
            "application step",
            "application, the next useful step",
            "appointment options and contact details",
            "admissions conversation",
        ]
        return any(term in content_lower for term in application_terms)

    def _resolve_known_application_programmes(self, query: str) -> list[str]:
        programme = self._extract_programme_from_text(query)
        if programme:
            return [programme]

        programme_interest = self._conversation_state.get("program_interest") or []
        normalised_interests = []
        for item in programme_interest:
            programme = self._normalise_programme_id(item)
            if programme and programme not in normalised_interests:
                normalised_interests.append(programme)
        if normalised_interests:
            return normalised_interests

        programme = self._normalise_programme_id(
            self._conversation_state.get("suggested_program")
        )
        if programme:
            return [programme]

        latest_ai = self._get_latest_ai_message_content()
        if self._text_mentions_multiple_programmes(latest_ai) or "alle drei" in latest_ai.lower():
            return ["emba", "iemba", "emba_x"]

        return []

    def _resolve_application_programmes(self, query: str) -> list[str]:
        if not self._is_application_next_step_request(query):
            return []

        programmes = self._resolve_known_application_programmes(query)
        if programmes:
            return programmes

        if self._latest_ai_mentions_multiple_programmes():
            return ["emba", "iemba", "emba_x"]

        return []

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

    def _build_programme_next_steps_response(self, language: str, programme: str) -> str:
        if programme == "emba_x":
            if language == "en":
                return (
                    "If **emba X** is currently the strongest option, the next step is not another programme overview. "
                    "It is a fit and admissions check.\n\n"
                    "1. **Clarify the development goal**: emba X is strongest when your next leadership step involves "
                    "digital transformation, Health-IT, MedTech, data/AI initiatives, innovation, or large organisational "
                    "change.\n"
                    "2. **Check formal fit**: recognised academic degree, **10+ years** professional experience, "
                    "**5+ years** leadership experience, and fluent English.\n"
                    "3. **Plan deadlines and tuition**: first application deadline **31 August 2026** with **CHF 99,000** "
                    "tuition; final application deadline **31 October 2026** with **CHF 110,000** tuition.\n"
                    "4. **Prepare the admissions conversation**: bring your CV, leadership scope, degree background, "
                    "English readiness, and one concrete transformation topic from your hospital context.\n\n"
                    "For the non-binding assessment and next steps, the right advisor is **Teyuna Giger** for **emba X**. "
                    "I can show appointment options and contact details below."
                )
            return (
                "Wenn **emba X** aktuell am besten klingt, ist der nächste Schritt keine weitere Programmbeschreibung, "
                "sondern eine Fit- und Zulassungsabklärung.\n\n"
                "1. **Ziel schärfen**: emba X passt besonders, wenn Ihr nächster Entwicklungsschritt mit Digitalisierung, "
                "Health-IT, MedTech, Daten/AI, Innovation oder grosser organisatorischer Transformation verbunden ist.\n"
                "2. **Formalen Fit prüfen**: anerkannter Hochschulabschluss, **10+ Jahre Berufserfahrung**, "
                "**5+ Jahre Führungserfahrung** und sehr gutes Englisch.\n"
                "3. **Fristen und Gebühren planen**: erste Bewerbungsfrist **31.08.2026** mit **CHF 99'000** "
                "Studiengebühr; finale Bewerbungsfrist **31.10.2026** mit **CHF 110'000** Studiengebühr.\n"
                "4. **Assessment-Gespräch vorbereiten**: CV, Führungsverantwortung, Studienabschluss, Englisch-Niveau "
                "und ein konkretes Transformationsvorhaben aus Ihrer Klinik-/Spitalpraxis mitbringen.\n\n"
                "Für die unverbindliche Einschätzung und die nächsten Bewerbungsschritte ist **Teyuna Giger** die "
                "passende Studienberaterin für **emba X**. Ich zeige Ihnen unten Terminoptionen und Kontaktdaten."
            )

        programme_details = {
            "emba": {
                "name": "EMBA HSG",
                "advisor": "Cyra von Müller",
                "focus_de": "General Management, Leadership und Unternehmensführung im DACH-Kontext",
                "focus_en": "general management, leadership, and executive decision-making in the DACH context",
                "fit_de": "anerkannter Hochschulabschluss, **5+ Jahre Berufserfahrung**, **3+ Jahre Führungserfahrung** und starke Deutschkenntnisse",
                "fit_en": "recognised degree, **5+ years** professional experience, **3+ years** leadership experience, and strong German",
                "timing_de": "Start **14.09.2026**, **18 Monate** berufsbegleitend, verlängerbar bis **48 Monate**, Studiengebühr **CHF 77'500**",
                "timing_en": "start **14 September 2026**, **18 months** part-time, extendable up to **48 months**, tuition **CHF 77,500**",
                "prepare_de": "CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Deutsch-Niveau, Entwicklungsziel und idealerweise eine erste Idee für ein Capstone-/Praxisprojekt",
                "prepare_en": "CV, degree certificates/transcripts, leadership scope, German readiness, development goal, and ideally an initial idea for a capstone/practice project",
            },
            "iemba": {
                "name": "IEMBA HSG",
                "advisor": "Kristin Fuchs",
                "focus_de": "internationale Managementperspektive, globale Peer Group und Führung über Märkte und Systeme hinweg",
                "focus_en": "international management perspective, a global peer group, and leadership across markets and systems",
                "fit_de": "anerkannter Hochschulabschluss, **5+ Jahre Berufserfahrung**, **3+ Jahre Führungserfahrung** und sehr gutes Englisch",
                "fit_en": "recognised degree, **5+ years** professional experience, **3+ years** leadership experience, and strong English",
                "timing_de": "Start **24.08.2026**, **18 Monate** berufsbegleitend, **10 Kernkurse**, **4 Wahlkurse**, **10 Präsenzwochen**, **4 Wochen Auslandsmodule**, Studiengebühr **CHF 85'000**",
                "timing_en": "start **24 August 2026**, **18 months** part-time, **10 core courses**, **4 electives**, **10 campus weeks**, **4 weeks abroad**, tuition **CHF 85,000**",
                "prepare_de": "CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Englisch-Niveau, internationale Zielsetzung und relevante Ausland-/Partner-/Markterfahrung",
                "prepare_en": "CV, degree certificates/transcripts, leadership scope, English readiness, international goals, and relevant cross-border, partner, or market experience",
            },
        }
        details = programme_details.get(programme)
        if not details:
            programme_name, advisor = "Executive MBA", "dem Admissions Team"
            if language == "en":
                return (
                    f"If **{programme_name}** is currently the strongest option, the next step is a fit and admissions "
                    "conversation rather than another overview. Check the formal requirements, prepare your CV, degree "
                    "background, leadership scope, language readiness, and the main goal you want to achieve through the "
                    f"programme. The appropriate advisor is **{advisor}**. I can show appointment options and contact details below."
                )
            return (
                f"Wenn **{programme_name}** aktuell am besten passt, ist der nächste Schritt ein Fit- und Zulassungsgespräch "
                "statt einer weiteren Übersicht. Sinnvoll vorzubereiten sind CV, Studienabschluss, Führungsverantwortung, "
                "Sprachniveau und das konkrete Entwicklungsziel, das Sie mit dem Programm erreichen möchten. "
                f"Die passende Studienberatung ist **{advisor}**. Ich zeige Ihnen unten Terminoptionen und Kontaktdaten."
            )

        if language == "en":
            return (
                f"If **{details['name']}** is currently the strongest option, the next step is a fit and admissions check.\n\n"
                f"1. **Clarify the development goal**: {details['name']} is strongest for {details['focus_en']}.\n"
                f"2. **Check formal fit**: {details['fit_en']}.\n"
                f"3. **Plan timing and tuition**: {details['timing_en']}.\n"
                f"4. **Prepare the admissions conversation**: bring {details['prepare_en']}.\n\n"
                f"The right advisor is **{details['advisor']}** for **{details['name']}**. I can show appointment options and contact details below."
            )
        return (
            f"Wenn **{details['name']}** aktuell am besten passt, ist der nächste Schritt eine Fit- und Zulassungsabklärung.\n\n"
            f"1. **Ziel schärfen**: {details['name']} passt besonders für {details['focus_de']}.\n"
            f"2. **Formalen Fit prüfen**: {details['fit_de']}.\n"
            f"3. **Timing und Gebühren planen**: {details['timing_de']}.\n"
            f"4. **Admissions-Gespräch vorbereiten**: {details['prepare_de']}.\n\n"
            f"Die passende Studienberatung ist **{details['advisor']}** für **{details['name']}**. Ich zeige Ihnen unten Terminoptionen und Kontaktdaten."
        )

    def _serve_programme_next_steps(
        self,
        processed_query: str,
        response_language: str,
        programme: str,
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving next-step guidance for selected programme: {programme}")
        response = self._build_programme_next_steps_response(response_language, programme)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        self._conversation_state['handover_requested'] = True
        self._conversation_state['suggested_program'] = programme

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=True,
            show_booking_widget=True,
            relevant_programs=[programme],
        )

    def _build_application_next_steps_response(self, language: str, programmes: list[str]) -> str:
        programme_labels = {
            "emba": ("EMBA HSG", "Cyra von Müller"),
            "iemba": ("IEMBA HSG", "Kristin Fuchs"),
            "emba_x": ("emba X", "Teyuna Giger"),
        }
        selected = [programme_labels[p] for p in programmes if p in programme_labels]

        if len(selected) == 1:
            programme_name, advisor = selected[0]
            if language == "en":
                return (
                    f"For the **{programme_name}** application, the next useful step is an admissions conversation with "
                    f"**{advisor}**. Prepare your CV, degree certificates, leadership scope, motivation, language readiness, "
                    "and your target start date. In that conversation, admissions can confirm formal eligibility, documents, "
                    "deadlines, and the best timing for submission.\n\n"
                    "I am showing the appointment options and contact details below."
                )
            return (
                f"Für die Bewerbung zum **{programme_name}** ist der nächste sinnvolle Schritt ein Zulassungs- und "
                f"Beratungsgespräch mit **{advisor}**. Vorbereiten sollten Sie CV, Studienabschluss, Umfang Ihrer "
                "Führungsverantwortung, Motivation, Sprachniveau und den gewünschten Startzeitpunkt. In dem Gespräch "
                "können formaler Fit, Unterlagen, Fristen und der beste Zeitpunkt für die Einreichung geklärt werden.\n\n"
                "Ich zeige Ihnen unten die Terminoptionen und Kontaktdaten."
            )

        if language == "en":
            return (
                "For the application step, the important point is to clarify the right programme before submitting "
                "documents. Prepare your CV, degree certificates, leadership scope, motivation, language readiness, and "
                "preferred start timing. Because more than one Executive MBA option is still relevant, I am showing the "
                "appointment options and contact details for all three programme advisors below."
            )

        return (
            "Für den Bewerbungsschritt sollte zuerst geklärt werden, welches der drei Executive-MBA-Programme wirklich "
            "das richtige Ziel ist. Vorbereiten sollten Sie CV, Studienabschluss, Führungsverantwortung, Motivation, "
            "Sprachniveau und den gewünschten Startzeitpunkt. Da noch mehrere Programme relevant sind, zeige ich Ihnen "
            "unten die Terminoptionen und Kontaktdaten für alle drei Studienberatungen."
        )

    def _serve_application_next_steps(
        self,
        processed_query: str,
        response_language: str,
        programmes: list[str],
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving application next-step guidance for programmes: {programmes}")
        response = self._build_application_next_steps_response(response_language, programmes)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        self._conversation_state["handover_requested"] = True
        if len(programmes) == 1:
            self._conversation_state["suggested_program"] = programmes[0]

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=True,
            show_booking_widget=True,
            relevant_programs=programmes,
        )

    def _build_application_process_details_response(self, language: str, programmes: list[str]) -> str:
        if len(programmes) == 1:
            programme = programmes[0]
            programme_names = {
                "emba": "EMBA HSG",
                "iemba": "IEMBA HSG",
                "emba_x": "emba X",
            }
            programme_name = programme_names.get(programme, "Executive MBA")

            if programme == "emba_x":
                if language == "en":
                    return (
                        f"The appointment options are already shown. For the **{programme_name}** application process, "
                        "the practical sequence is:\n\n"
                        "1. **Fit check**: confirm recognised degree, **10+ years** professional experience, **5+ years** "
                        "leadership experience, and fluent English.\n"
                        "2. **Prepare documents**: CV, degree certificates/transcripts, overview of leadership scope, "
                        "motivation and goals for emba X, English readiness, and one concrete transformation topic you "
                        "could discuss in admissions.\n"
                        "3. **Plan timing**: first application deadline **31 August 2026** with **CHF 99,000** tuition; "
                        "final deadline **31 October 2026** with **CHF 110,000** tuition.\n"
                        "4. **Admissions assessment**: discuss fit, motivation, leadership responsibility, English level, "
                        "and whether emba X is the right programme for your goals.\n"
                        "5. **Decision and enrolment**: after admissions confirmation, finalise participation, timing, and "
                        "tuition/payment details."
                    )
                return (
                    f"Die Terminoptionen sind bereits eingeblendet. Für die Bewerbung zum **{programme_name}** läuft der "
                    "Prozess praktisch so:\n\n"
                    "1. **Fit prüfen**: anerkannter Hochschulabschluss, **10+ Jahre Berufserfahrung**, **5+ Jahre "
                    "Führungserfahrung** und sehr gutes Englisch.\n"
                    "2. **Unterlagen vorbereiten**: CV, Studienabschluss/Zeugnisse, Übersicht zur Führungsverantwortung, "
                    "Motivation und Ziele für emba X, Englisch-Niveau sowie ein konkretes Transformationsvorhaben, das "
                    "Sie im Admissions-Gespräch besprechen können.\n"
                    "3. **Timing planen**: erste Bewerbungsfrist **31.08.2026** mit **CHF 99'000** Studiengebühr; finale "
                    "Bewerbungsfrist **31.10.2026** mit **CHF 110'000** Studiengebühr.\n"
                    "4. **Admissions-/Assessment-Gespräch**: Fit, Motivation, Führungsverantwortung, Englisch-Niveau und "
                    "Zielsetzung werden geprüft.\n"
                    "5. **Entscheid und Einschreibung**: nach positiver Rückmeldung werden Teilnahme, Startzeitpunkt und "
                    "Zahlungs-/Gebührenthemen finalisiert."
                )

            programme_process_details = {
                "emba": {
                    "requirements_de": "Hochschulabschluss, **5+ Jahre Berufserfahrung**, **3+ Jahre Führungserfahrung** und starke Deutschkenntnisse",
                    "requirements_en": "university degree, **5+ years** professional experience, **3+ years** leadership experience, and strong German",
                    "documents_de": "CV, Studienabschluss/Zeugnisse, Übersicht zur Führungsverantwortung, Motivation, Entwicklungsziele, Deutsch-Niveau und idealerweise eine erste Idee für ein Capstone-/Praxisprojekt",
                    "documents_en": "CV, degree certificates/transcripts, overview of leadership scope, motivation, development goals, German readiness, and ideally an initial idea for a capstone/practice project",
                    "timing_de": "Start **14.09.2026**, **18 Monate** berufsbegleitend, verlängerbar bis **48 Monate**, Studiengebühr **CHF 77'500**. Aktuelle Bewerbungsfristen und verfügbare Plätze sollten im Zulassungsgespräch bestätigt werden",
                    "timing_en": "start **14 September 2026**, **18 months** part-time, extendable up to **48 months**, tuition **CHF 77,500**. Current application deadlines and available seats should be confirmed in the admissions conversation",
                },
                "iemba": {
                    "requirements_de": "Hochschulabschluss, **5+ Jahre Berufserfahrung**, **3+ Jahre Führungserfahrung** und sehr gutes Englisch",
                    "requirements_en": "university degree, **5+ years** professional experience, **3+ years** leadership experience, and strong English",
                    "documents_de": "CV, Studienabschluss/Zeugnisse, Übersicht zur Führungsverantwortung, Motivation, internationale Zielsetzung, Englisch-Niveau und relevante Ausland-/Partner-/Markterfahrung",
                    "documents_en": "CV, degree certificates/transcripts, overview of leadership scope, motivation, international goals, English readiness, and relevant cross-border, partner, or market experience",
                    "timing_de": "Start **24.08.2026**, **18 Monate** berufsbegleitend, **10 Kernkurse**, **4 Wahlkurse**, **10 Präsenzwochen**, **4 Wochen Auslandsmodule**, Studiengebühr **CHF 85'000**. Aktuelle Bewerbungsfristen und verfügbare Plätze sollten im Zulassungsgespräch bestätigt werden",
                    "timing_en": "start **24 August 2026**, **18 months** part-time, **10 core courses**, **4 electives**, **10 campus weeks**, **4 weeks abroad**, tuition **CHF 85,000**. Current application deadlines and available seats should be confirmed in the admissions conversation",
                },
            }
            details = programme_process_details.get(programme)

            if language == "en":
                if details:
                    return (
                        f"The appointment options are already shown. For the **{programme_name}** application process, the "
                        "practical sequence is:\n\n"
                        f"1. **Fit check**: {details['requirements_en']}.\n"
                        f"2. **Prepare documents**: {details['documents_en']}.\n"
                        f"3. **Plan timing and tuition**: {details['timing_en']}.\n"
                        "4. **Admissions conversation**: confirm formal eligibility, programme fit, goals, timing, current "
                        "application deadlines, and open questions about the application file.\n"
                        "5. **Submit application and enrol**: admissions confirms the exact submission route, missing "
                        "documents, decision process, enrolment steps, and payment details."
                    )
                return (
                    f"The appointment options are already shown. For the **{programme_name}** application process, the "
                    "practical sequence is:\n\n"
                    "1. **Fit check**: university degree, professional experience, leadership experience, and language readiness.\n"
                    "2. **Prepare documents**: CV, degree certificates/transcripts, overview of leadership scope, "
                    "motivation and development goals, and language readiness.\n"
                    "3. **Admissions conversation**: confirm formal eligibility, programme fit, goals, timing, and open "
                    "questions about the application file.\n"
                    "4. **Submit application**: admissions confirms the exact submission route, missing documents, and "
                    "current deadlines.\n"
                    "5. **Decision and enrolment**: after admission, finalise participation, start timing, and tuition/payment details."
                )
            if details:
                return (
                    f"Die Terminoptionen sind bereits eingeblendet. Für die Bewerbung zum **{programme_name}** läuft der Prozess "
                    "praktisch so:\n\n"
                    f"1. **Fit prüfen**: {details['requirements_de']}.\n"
                    f"2. **Unterlagen vorbereiten**: {details['documents_de']}.\n"
                    f"3. **Timing und Gebühren planen**: {details['timing_de']}.\n"
                    "4. **Zulassungs-/Beratungsgespräch**: formaler Fit, Programm-Fit, Ziele, Timing, aktuelle "
                    "Bewerbungsfristen und offene Fragen zur Bewerbungsakte klären.\n"
                    "5. **Bewerbung einreichen und Einschreibung finalisieren**: Admissions bestätigt den genauen "
                    "Einreichungsweg, fehlende Unterlagen, Entscheidungsprozess, Einschreibung und Zahlungs-/Gebührenthemen."
                )
            return (
                f"Die Terminoptionen sind bereits eingeblendet. Für die Bewerbung zum **{programme_name}** läuft der Prozess "
                "praktisch so:\n\n"
                "1. **Fit prüfen**: Hochschulabschluss, Berufserfahrung, Führungserfahrung und Sprachkenntnisse.\n"
                "2. **Unterlagen vorbereiten**: CV, Studienabschluss/Zeugnisse, Übersicht zur Führungsverantwortung, "
                "Motivation und Entwicklungsziele sowie Sprachniveau.\n"
                "3. **Zulassungs-/Beratungsgespräch**: formaler Fit, Programm-Fit, Ziele, Timing und offene Fragen zur "
                "Bewerbungsakte klären.\n"
                "4. **Bewerbung einreichen**: Admissions bestätigt den genauen Einreichungsweg, fehlende Unterlagen und "
                "aktuelle Fristen.\n"
                "5. **Entscheid und Einschreibung**: nach positiver Zulassung Teilnahme, Startzeitpunkt und Zahlungs-/Gebührenthemen finalisieren."
            )

        if language == "en":
            return (
                "The appointment options are already shown. Before applying, first decide which programme you want to "
                "target. The process then follows the same structure: fit check, documents, admissions conversation, "
                "application submission, decision, and enrolment.\n\n"
                "**EMBA HSG**: start **14 September 2026**, tuition **CHF 77,500**, requires degree, **5+ years** "
                "professional experience, **3+ years** leadership experience, and strong German.\n"
                "**IEMBA HSG**: start **24 August 2026**, tuition **CHF 85,000**, requires degree, **5+ years** "
                "professional experience, **3+ years** leadership experience, and strong English.\n"
                "**emba X**: first application deadline **31 August 2026** with **CHF 99,000** tuition; final deadline "
                "**31 October 2026** with **CHF 110,000** tuition; requires degree, **10+ years** professional experience, "
                "**5+ years** leadership experience, and fluent English.\n\n"
                "For all three: prepare CV, degree certificates/transcripts, leadership overview, motivation, language "
                "readiness, and preferred start timing."
            )
        return (
            "Die Terminoptionen sind bereits eingeblendet. Vor der Bewerbung sollte zuerst geklärt werden, welches Programm "
            "Sie konkret ansteuern. Danach ist der Ablauf grundsätzlich: Fit prüfen, Unterlagen vorbereiten, "
            "Zulassungs-/Beratungsgespräch, Bewerbung einreichen, Entscheid und Einschreibung.\n\n"
            "**EMBA HSG**: Start **14.09.2026**, Studiengebühr **CHF 77'500**, Hochschulabschluss, **5+ Jahre "
            "Berufserfahrung**, **3+ Jahre Führungserfahrung** und starke Deutschkenntnisse.\n"
            "**IEMBA HSG**: Start **24.08.2026**, Studiengebühr **CHF 85'000**, Hochschulabschluss, **5+ Jahre "
            "Berufserfahrung**, **3+ Jahre Führungserfahrung** und sehr gutes Englisch.\n"
            "**emba X**: erste Bewerbungsfrist **31.08.2026** mit **CHF 99'000** Studiengebühr; finale Bewerbungsfrist "
            "**31.10.2026** mit **CHF 110'000** Studiengebühr; Hochschulabschluss, **10+ Jahre Berufserfahrung**, "
            "**5+ Jahre Führungserfahrung** und sehr gutes Englisch.\n\n"
            "Für alle drei sollten Sie CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Motivation, Sprachniveau "
            "und gewünschten Startzeitpunkt vorbereiten."
        )

    def _serve_application_process_details(
        self,
        processed_query: str,
        response_language: str,
        programmes: list[str],
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving application process details for programmes: {programmes}")
        response = self._build_application_process_details_response(response_language, programmes)
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
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
            relevant_programs=programmes,
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

    def _build_programme_overview_response(
        self,
        language: str,
        detailed: bool,
        profile_context: bool = False,
    ) -> str:
        if language == 'en':
            if not detailed:
                if not profile_context:
                    return (
                        "At HSG, there are three relevant Executive MBA options. The main difference is not that one is "
                        "universally better, but their language, focus, network, and development goal.\n\n"
                        "1. **EMBA HSG**: German-speaking, DACH-focused general management programme. It is part-time, "
                        "**18 months** long, extendable up to **48 months**, with **9 core courses**, **5 electives**, "
                        "about **14 campus weeks**, a capstone project, and **CHF 77,500** tuition. Goal: strengthen "
                        "strategy, finance, organisation, and leadership capability in the German-speaking market.\n\n"
                        "2. **IEMBA HSG**: English-speaking international Executive MBA. It is part-time, **18 months** "
                        "long, with **10 core courses**, **4 electives**, **10 campus weeks**, **4 weeks abroad**, a "
                        "thesis, and **CHF 85,000** tuition. Goal: build international management perspective, global "
                        "peer learning, and leadership confidence across markets and systems.\n\n"
                        "3. **emba X**: English-speaking joint degree from **ETH Zurich** and the **University of St.Gallen**. "
                        "It is part-time, **18 months**, blended across Zurich and St.Gallen, focused on business, "
                        "technology, innovation, and transformation. Tuition is **CHF 99,000 / CHF 110,000** depending "
                        "on the application deadline. Goal: lead at the intersection of management, technology, and change."
                    )

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
                if not profile_context:
                    return (
                        "More detail across all three programmes:\n\n"
                        "**EMBA HSG** aims to strengthen broad general-management judgement in the DACH context. It is "
                        "the most natural fit if the goal is stronger strategic, financial, organisational, governance, "
                        "negotiation, and leadership capability in German-speaking organisations.\n\n"
                        "**IEMBA HSG** aims to build international management perspective. The value is not only the "
                        "English language; it is the global cohort, international modules, and broader comparison across "
                        "markets, systems, and leadership environments.\n\n"
                        "**emba X** aims at leadership where business and technology meet. It is the strongest option if "
                        "the goal is digital transformation, innovation, technology-driven business models, AI/data "
                        "initiatives, or large organisational change. Its distinctive feature is the integrated **ETH "
                        "Zurich** plus **University of St.Gallen** joint-degree setting and access to both networks."
                    )

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

            if not profile_context:
                return (
                    "The next useful distinction is by goals and working context:\n\n"
                    "- Choose **EMBA HSG** if the main goal is DACH-focused general management: strategy, finance, "
                    "governance, organisation, negotiation, and leadership.\n"
                    "- Choose **IEMBA HSG** if the main goal is international exposure: global peer learning, "
                    "international modules, markets, organisations, and partnerships.\n"
                    "- Choose **emba X** if the main goal is technology-led transformation: digitalisation, innovation, "
                    "data/AI initiatives, new business models, or major change programmes.\n\n"
                    "The next step is therefore not an automatic recommendation, but clarifying the development goal: "
                    "DACH management depth, international management breadth, or technology-led transformation."
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
            if not profile_context:
                return (
                    "Bei HSG gibt es drei relevante Executive-MBA-Optionen. Der Unterschied liegt nicht darin, dass ein "
                    "Programm pauschal besser ist, sondern in Sprache, Fokus, Netzwerk und Entwicklungsziel.\n\n"
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
            if not profile_context:
                return (
                    "Weitere Details zu **allen drei Programmen**:\n\n"
                    "**EMBA HSG** zielt auf breite General-Management-Kompetenz im DACH-Raum. Das Programm ist sinnvoll, "
                    "wenn Sie Strategie, Finanzen, Governance, Organisation, Verhandlung und Change Management im "
                    "deutschsprachigen Kontext vertiefen möchten. Das Capstone-Projekt kann auf ein reales "
                    "Organisations- oder Transformationsvorhaben ausgerichtet werden.\n\n"
                    "**IEMBA HSG** zielt auf internationale Managementkompetenz. Der Mehrwert liegt in der englischsprachigen "
                    "globalen Kohorte, den internationalen Modulen und dem Vergleich verschiedener Märkte, Systeme und "
                    "Führungsumfelder.\n\n"
                    "**emba X** zielt auf Führung an der Schnittstelle von Business und Technologie. Das ist besonders "
                    "relevant, wenn Ihre Ziele Digitalisierung, datengetriebene Prozesse, Innovation, neue Geschäftsmodelle "
                    "oder grosse Transformationsprojekte betreffen. Der besondere Punkt ist die Kombination aus **ETH Zürich** "
                    "und **Universität St.Gallen** sowie der Zugang zu beiden Netzwerken."
                )

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

        if not profile_context:
            return (
                "Die nächste sinnvolle Unterscheidung läuft über Ziele und Arbeitskontext:\n\n"
                "- **EMBA HSG** passt am besten, wenn der Schwerpunkt auf General Management im DACH-Raum liegt: "
                "Strategie, Finanzen, Governance, Organisation, Verhandlung und Leadership.\n"
                "- **IEMBA HSG** passt am besten, wenn Internationalität zentral ist: globale Peer Group, "
                "Auslandsmodule, internationale Märkte, Organisationen und Partnerschaften.\n"
                "- **emba X** passt am besten, wenn Technologie und Transformation im Zentrum stehen: Digitalisierung, "
                "Innovation, Daten-/AI-Projekte, neue Geschäftsmodelle oder grosse Veränderungsprogramme.\n\n"
                "Der nächste Schritt ist daher nicht eine pauschale Empfehlung, sondern die Klärung Ihres Ziels: "
                "DACH-Management, Internationalität oder technologiegetriebene Transformation."
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
        profile_context: bool = False,
    ) -> LeadAgentQueryResponse:
        chain_logger.info("Serving deterministic three-programme overview without a model call.")
        response = self._build_programme_overview_response(
            response_language,
            detailed=detailed,
            profile_context=profile_context,
        )
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._programme_overview_profile_context = profile_context
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
