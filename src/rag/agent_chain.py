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
from time import perf_counter

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
from src.rag.programme_facts import JsonProgrammeFactsProvider, ProgrammeFacts, ProgrammeFactsProvider
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian
from src.rag.language_detection import LanguageDetector
from src.rag.tool_schemas import RetrieveContextInput

from src.utils.logging import get_logger
from src.utils.lang import get_language_name
from src.utils.conversation_tracker import ConversationTurnTracker
from src.config import config

from ..cache.cache import Cache

chain_logger = get_logger('rag.agent_chain')

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
        self._programme_facts_provider = JsonProgrammeFactsProvider(self._retrieve_context_via_tool)

        if config.chain.EVALUATE_RESPONSE_QUALITY:
            from src.rag.quality_score_handler import QualityScoreHandler
            self._quality_handler = QualityScoreHandler()

        self._language_detector = LanguageDetector()

        # Generate unique user ID for this session
        self._user_id = session_id or str(uuid.uuid4())
        self._conversation_tracker = ConversationTurnTracker(session_id=self._user_id)

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

        # Track repeated fallback/redirect uses for escalation.
        self._fallback_counters = {
            "invalid_input": 0,
            "aggressive": 0,
            "scope_violations": {},
        }

        chain_logger.info(f"Initialized new Agent Chain for language '{language}' with user_id: {self._user_id}")

    @staticmethod
    def _subagent_retrieval_fallback(program: str) -> str:
        fallback_by_program = {
            'emba': (
                "Die Kontextdatenbank ist momentan nicht verfuegbar. Ich kann deshalb keine "
                "aktuellen Fakten zum **EMBA HSG** nachladen und sollte keine Preise, Daten "
                "oder Zulassungsdetails aus statischem Code nennen."
            ),
            'iemba': (
                "Die Kontextdatenbank ist momentan nicht verfuegbar. Ich kann deshalb keine "
                "aktuellen Fakten zum **IEMBA HSG** nachladen und sollte keine Preise, Daten "
                "oder Zulassungsdetails aus statischem Code nennen."
            ),
            'embax': (
                "Die Kontextdatenbank ist momentan nicht verfuegbar. Ich kann deshalb keine "
                "aktuellen Fakten zu **emba X** nachladen und sollte keine Preise, Daten "
                "oder Zulassungsdetails aus statischem Code nennen."
            ),
        }
        return fallback_by_program[program]

    def _retrieve_context(self, query: str, program: str, language: str = None):
        """
        Send the query to the vector database to retrieve additional information about the program.

        Args:
            query: Keywords depicting information you want to retrieve in the primary language.
            program: Name of the program (either 'emba', 'iemba' or 'emba x') for which the information is requested.
            language: Set to 'en' for IEMBA and emba x. set to 'de' for EMBA HSG. This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language.         
        """
        lang = language if language in ['en', 'de'] else self._initial_language
        normalized_program = self._normalise_programme_id(program)
        property_filters = (
            {'programs': [normalized_program]}
            if normalized_program
            else None
        )
        retrieval_started = perf_counter()
        weaviate_response_time = None
        try:
            response, weaviate_response_time = self._dbservice.query(
                query,
                lang,
                property_filters=property_filters,
                limit=config.get('TOP_K_RETRIEVAL'),
            )
            serialized = '\n\n'.join([doc.properties.get('body', '') for doc in response.objects])
            self._conversation_tracker.record_retrieve_context_call(
                query=query,
                program=normalized_program or program,
                language=lang,
                response_time_seconds=perf_counter() - retrieval_started,
                weaviate_response_time_seconds=weaviate_response_time,
            )
            return serialized
        except Exception as e:
            self._conversation_tracker.record_retrieve_context_call(
                query=query,
                program=normalized_program or program,
                language=lang,
                response_time_seconds=perf_counter() - retrieval_started,
                weaviate_response_time_seconds=weaviate_response_time,
                success=False,
                error=str(e),
            )
            raise e

    @traceable(name="retrieve_context")
    def _retrieve_context_via_tool(self, query: str, program: str, language: str = None) -> str:
        """Invoke the LangChain retrieval tool so deterministic fact paths are traceable."""
        retrieve_tool = getattr(self, "_retrieve_context_tool", None)
        if retrieve_tool is None:
            return self._retrieve_context(query=query, program=program, language=language)
        return retrieve_tool.invoke(
            {
                "query": query,
                "program": program,
                "language": language,
            }
        )


    def _init_agents(self):
        from .subagents import SubagentProvider
        if config.chain.ENABLE_SUBAGENTS:
            chain_logger.warning("Subagents activated! This might lead to high response times!")

        sub_provider = SubagentProvider(self._initial_language, self._query, self._retrieve_context)

        run_config: RunnableConfig = {
            'configurable': {'thread_id': 0}
        }
        fallback_middleware = ModelFallbackMiddleware(
            *modelconf.get_fallback_models()
        )
        tool_retrieve_context = tool(
            name_or_callable='retrieve_context',
            runnable=self._retrieve_context,
            args_schema=RetrieveContextInput,
            description=(
                "Retrieve current programme context from the vector database. "
                "Arguments: query, program, optional language."
            ),
            return_direct=False,
            parse_docstring=False,
        )
        self._retrieve_context_tool = tool_retrieve_context

        if config.chain.ENABLE_SUBAGENTS:
            lead_agent_tools = sub_provider.get_subagent_tools()
        else:
            lead_agent_tools = [tool_retrieve_context]

        agents = {
            'lead': create_agent(
                name="lead_agent",
                model=modelconf.get_main_agent_model(),
                tools=lead_agent_tools,
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(
                    'lead',
                    language=self._initial_language,
                    use_subagents=config.chain.ENABLE_SUBAGENTS
                ),
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
        if config.chain.ENABLE_SUBAGENTS:
            agents |= sub_provider.get_subagents(fallback_middleware)

        return agents, run_config


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

    def generate_greeting(self) -> str:
        greeting_message = random.choice(GREETING_MESSAGES[self._stored_language])
        return greeting_message

    @traceable
    def query(self, query: str) -> LeadAgentQueryResponse:
        return self._conversation_tracker.track_turn(
            user_query=query,
            callback=lambda: self._query_impl(query),
        )

    def _query_impl(self, query: str) -> LeadAgentQueryResponse:
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
        input_result = InputHandler.process_input_with_metadata(
            query,
            [msg for msg in self._conversation_history if isinstance(msg, (HumanMessage, AIMessage))]
        )
        processed_query, is_valid = input_result.processed_message, input_result.is_valid
        self._conversation_tracker.record_input_handler(
            processed_query=processed_query,
            is_valid=is_valid,
            fallback_triggered=input_result.fallback_triggered,
            fallback_category=input_result.fallback_category,
        )

        if not is_valid or not processed_query:
            chain_logger.warning(f"Invalid input received: '{query}'")
            self._fallback_counters["invalid_input"] += 1
            invalid_response = (
                get_repeated_not_valid_query_message(self._stored_language)
                if self._fallback_counters["invalid_input"] >= 2
                else NOT_VALID_QUERY_MESSAGE[self._stored_language]
            )
            return LeadAgentQueryResponse(
                response=invalid_response,
                language=current_language,
                processed_query=query
            )

        self._fallback_counters["invalid_input"] = 0

        # Log check
        if processed_query != query:
            chain_logger.info(f"Interpreted input '{query}' as '{processed_query}'")

        # 3. Language Detection
        # First: Check for explicit language switch request (overrides lock)
        language_detection_started = perf_counter()
        language_detection_response = current_language
        language_detection_method = None
        explicit_switch = self._language_detector.detect_explicit_switch_request(processed_query)
        if explicit_switch:
            self._stored_language = explicit_switch
            current_language = explicit_switch
            self._conversation_state['user_language'] = explicit_switch
            language_detection_response = explicit_switch
            language_detection_method = "explicit_switch"
        elif self._language_detector.is_language_neutral_program_reference(processed_query):
            chain_logger.info(
                f"Skipping language re-detection for language-neutral programme reference: '{processed_query}'"
            )
            current_language = self._stored_language
            language_detection_response = current_language
            language_detection_method = "skipped_language_neutral_programme_reference"
        else:
            # Count user messages in conversation history
            user_message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])

            # Lock language after N user messages (allows language switch early in conversation)
            lang_lock_n = config.convstate.LOCK_LANGUAGE_AFTER_N_MESSAGES
            if lang_lock_n > 0 and user_message_count >= lang_lock_n:
                chain_logger.info(f"Language locked to '{self._stored_language}' (after {user_message_count} messages)")
                current_language = self._stored_language
                language_detection_response = current_language
                language_detection_method = "locked"
            else:
                detected_language = self._language_detector.detect_language(processed_query)
                self._conversation_state['user_language'] = detected_language
                language_detection_response = detected_language
                language_detection_method = "detected"

                # Language validation
                if detected_language in ['de', 'en']:
                    self._stored_language = detected_language
                    current_language = detected_language
                else:
                    chain_logger.info("Invalid language detected.")
                    self._conversation_tracker.record_language_detection(
                        response=language_detection_response,
                        duration_seconds=perf_counter() - language_detection_started,
                        method=language_detection_method,
                    )
                    return LeadAgentQueryResponse(
                        response=LANGUAGE_FALLBACK_MESSAGE[current_language],
                        language=current_language,
                        processed_query=processed_query
                    )

        self._conversation_tracker.record_language_detection(
            response=language_detection_response,
            duration_seconds=perf_counter() - language_detection_started,
            method=language_detection_method,
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

        if self._is_iemba_embax_tech_career_change_request(processed_query):
            return self._serve_iemba_embax_tech_career_guidance(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._is_iemba_eligibility_assessment_request(processed_query):
            return self._serve_iemba_eligibility_assessment(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._is_iemba_visa_request(processed_query):
            return self._serve_iemba_visa_response(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._is_iemba_apac_alumni_request(processed_query):
            return self._serve_iemba_apac_alumni_response(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._is_mixed_language_programme_overview_request(processed_query):
            return self._serve_mixed_language_programme_overview(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._is_emba_minimal_profile_guidance_request(processed_query):
            return self._serve_emba_minimal_profile_guidance(
                processed_query=processed_query,
                response_language=current_language,
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

        if self._is_embax_comparison_request(processed_query):
            return self._serve_embax_comparison_response(
                processed_query=processed_query,
                response_language=current_language,
            )

        if self._is_embax_language_request(processed_query):
            return self._serve_embax_language_response(
                processed_query=processed_query,
                response_language=current_language,
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

        fact_programmes = self._resolve_programmes_for_fact_request(processed_query)
        if fact_programmes:
            return self._serve_programme_fact_request(
                processed_query=processed_query,
                response_language=current_language,
                programmes=fact_programmes,
            )

        if self._is_price_frustration_request(processed_query):
            return self._serve_price_frustration_response(
                processed_query=processed_query,
                response_language=current_language,
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
                self._fallback_counters["aggressive"] += 1
                attempt_count = self._fallback_counters["aggressive"]
            else:
                scope_violations = self._fallback_counters["scope_violations"]
                scope_violations[scope_type] = scope_violations.get(scope_type, 0) + 1
                attempt_count = scope_violations[scope_type]

            should_escalate, escalation_type = ScopeGuardian.should_escalate(
                processed_query, scope_type, attempt_count
            )

            if should_escalate:
                redirect_msg = ScopeGuardian.get_escalation_message(escalation_type, current_language)
            else:
                redirect_msg = ScopeGuardian.get_redirect_message(scope_type, current_language)
                if scope_type == "off_topic":
                    redirect_msg = self._append_cost_orientation_to_redirect(
                        redirect_msg,
                        current_language,
                    )

            self._conversation_history.append(HumanMessage(processed_query))
            self._conversation_history.append(AIMessage(redirect_msg))

            return LeadAgentQueryResponse(
                response=redirect_msg,
                language=current_language,
                processed_query=processed_query,
                appointment_requested=False,
                show_booking_widget=False,
            )

        if self._is_likely_too_early_for_executive_mba(processed_query):
            return self._serve_too_early_for_executive_mba(
                processed_query=processed_query,
                response_language=current_language,
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
                    additional_details=cached_data.get("additional_details", ""),
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
                    "additional_details":    response.additional_details,
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
        # Reset redirect counters after a valid on-topic query reaches the agent.
        self._fallback_counters["scope_violations"] = {}
        
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
        additional_details = ResponseFormatter.clean_response(
            ResponseFormatter.remove_tables(structured_response.additional_details or "")
        )
        chain_logger.info(f"Is answer context dependent: {structured_response.is_context_dependent}")
        chain_logger.info(f"Additional details returned: {bool(additional_details)}")
        chain_logger.info(f"Appointment Requested: {structured_response.appointment_requested}")
        chain_logger.info(f"Show Booking Widget: {structured_response.show_booking_widget}")
        chain_logger.info(f"Relevant Programs: {structured_response.relevant_programs}")
        self._conversation_tracker.record_structured_agent_output(
            structured_response,
            additional_details=additional_details,
        )

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
        if config.chain.EVALUATE_RESPONSE_QUALITY:
            quality_evaluation = self._quality_handler.evaluate_response_quality(preprocessed_query, formatted_response)

            chain_logger.info(f"Quality Score: {quality_evaluation.overall_score:1.2f}")

            if quality_evaluation.overall_score < config.chain.CONFIDENCE_THRESHOLD:
                confidence_fallback = True
                formatted_response = CONFIDENCE_FALLBACK_MESSAGE[response_language]
                chain_logger.info("Fallback Mechanism activated!")

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

        booking_flow_requested = (
            explicit_booking_intent
            or booking_preference_follow_up
        )
        appointment_requested = bool(booking_flow_requested)
        show_booking_widget = bool(
            booking_flow_requested and (
                structured_response.show_booking_widget
                or self._response_commits_to_showing_booking_widget(formatted_response)
            )
        )

        if structured_response.appointment_requested and not booking_flow_requested:
            chain_logger.info("Suppressed booking state because no explicit booking intent was detected.")
        elif booking_preference_follow_up and show_booking_widget:
            chain_logger.info("Continuing active booking flow and showing booking widget for a preference follow-up.")
        
        return LeadAgentQueryResponse(
            response = formatted_response,
            additional_details = additional_details,
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

        if re.search(r"(?<!i)\bemba hsg\b", text_lower) or re.search(r"\bgerman(?:-speaking)?\s+emba\b", text_lower):
            programmes.append("emba")
        if "iemba" in text_lower or "international emba" in text_lower:
            programmes.append("iemba")
        if "emba x" in text_lower or "embax" in text_lower:
            programmes.append("emba_x")

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

    def _is_application_next_step_route(self, query: str) -> bool:
        """Return True for process/next-step application questions, not deadline-only fact questions."""
        if not self._is_application_next_step_request(query):
            return False

        query_lower = query.lower()
        timing_or_price_terms = [
            "wann",
            "frist",
            "fristen",
            "bewerbungsfrist",
            "bewerbungszeitraum",
            "bewerbungsperiode",
            "deadline",
            "deadlines",
            "application deadline",
            "application period",
            "start",
            "startdatum",
            "beginnt",
            "startet",
            "kosten",
            "kostet",
            "preis",
            "gebühr",
            "gebuehr",
            "chf",
            "dauer",
            "wie lange",
        ]
        process_terms = [
            "wie bewerbe ich mich",
            "wie kann ich mich",
            "wie bewirbt man sich",
            "wie läuft die bewerbung",
            "wie laeuft die bewerbung",
            "bewerbungsprozess",
            "bewerbungsablauf",
            "prozess",
            "ablauf",
            "schritte",
            "unterlagen",
            "dokument",
            "dokumente",
            "zulassung",
            "assessment",
            "how do i apply",
            "how can i apply",
            "how to apply",
            "application process",
            "admissions process",
            "application steps",
            "application documents",
            "documents",
        ]

        if any(term in query_lower for term in process_terms):
            return True

        if re.search(r"\bwie\b.{0,100}\b(bewerben|bewerbe|bewerbung|bewirbt)\b", query_lower):
            return True
        if re.search(r"\bhow\b.{0,100}\b(apply|application|admission|admissions)\b", query_lower):
            return True

        if any(term in query_lower for term in timing_or_price_terms):
            return False

        return any(
            term in query_lower
            for term in ["bewerben", "bewerbung", "apply", "application", "admission", "admissions"]
        )

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
        if self._is_explicit_booking_intent(query):
            return []

        if not self._is_application_next_step_route(query):
            return []

        programmes = self._resolve_known_application_programmes(query)
        if programmes:
            return programmes

        if self._latest_ai_mentions_multiple_programmes():
            return ["emba", "iemba", "emba_x"]

        return []

    def _append_deterministic_response(
        self,
        processed_query: str,
        response: str,
        response_language: str,
        relevant_programs: list[str] | None = None,
        suggested_program: str | None = None,
    ) -> LeadAgentQueryResponse:
        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))

        if hasattr(self, "_conversation_state"):
            if suggested_program is not None:
                self._conversation_state["suggested_program"] = suggested_program
            if relevant_programs:
                program_interest = self._conversation_state.setdefault("program_interest", [])
                if program_interest is not None:
                    for programme in relevant_programs:
                        if programme not in program_interest:
                            program_interest.append(programme)

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=relevant_programs or [],
        )

    def _is_emba_minimal_profile_guidance_request(self, query: str) -> bool:
        query_lower = query.lower()
        context_lower = self._human_context_for_recommendation(query)
        has_emba_context = (
            "executive mba" in context_lower
            or "emba hsg" in context_lower
            or "berufsbegleitend" in context_lower
        )
        has_minimum_profile = (
            ("6 jahre" in context_lower and "3 jahre" in context_lower)
            or ("6 years" in context_lower and "3 years" in context_lower)
        )
        asks_fit = any(
            term in query_lower
            for term in [
                "infrage",
                "ausreicht",
                "chancen",
                "qualify",
                "eligible",
                "chances",
            ]
        )
        return has_emba_context and has_minimum_profile and asks_fit

    def _serve_emba_minimal_profile_guidance(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        query_lower = processed_query.lower()
        if response_language == "de":
            if "chancen" in query_lower:
                response = (
                    "Mit **6 Jahren Berufserfahrung** und **3 Jahren Teamleitung** liegen Sie grundsätzlich im "
                    "passenden Bereich für den **EMBA HSG**. Eine Zusage kann ich daraus nicht ableiten; gute Chancen "
                    "hängen vor allem davon ab, ob Ihre Führung substanziell ist.\n\n"
                    "Wichtig für die Einschätzung sind Teamgrösse, direkte Personalverantwortung, Budget- oder "
                    "Projektverantwortung, Entscheidungsspielraum und Entwicklung Ihrer Rolle. Der Zulassungsausschuss "
                    "prüft das individuell; für einen Grenzfall ist eine kurze Profilprüfung durch Admissions sinnvoll."
                )
            elif "ausreicht" in query_lower:
                response = (
                    "Ihre **3 Jahre Führungserfahrung** erfüllen die typische Mindestmarke für den **EMBA HSG**, aber "
                    "die Qualität der Führung ist entscheidend. Admissions schaut nicht nur auf Jahre, sondern auf "
                    "Personalverantwortung, Teamgrösse, Projekt-/Budgetverantwortung und Entscheidungsspielraum.\n\n"
                    "Wenn Ihre Teamleitung echte Verantwortung umfasst, wirkt Ihr Profil grundsätzlich plausibel. Wenn "
                    "es eher fachliche Koordination ohne Entscheidungsmandat ist, sollte Admissions den Fit prüfen."
                )
            else:
                response = (
                    "Ja, grundsätzlich kommen Sie für den **EMBA HSG** infrage: **6 Jahre Berufserfahrung** und "
                    "**3 Jahre Teamleitung** treffen die zentralen Erfahrungsanforderungen. Die finale Zulassung hängt "
                    "aber vom Gesamtprofil ab.\n\n"
                    "Für die Prüfung zählen besonders anerkannter Hochschulabschluss, Art und Umfang Ihrer "
                    "Führungsverantwortung, Motivation, Deutschkenntnisse und ob das berufsbegleitende Format zu Ihrer "
                    "aktuellen Rolle passt."
                )
        else:
            response = (
                "With **6 years of professional experience** and **3 years of team leadership**, you are broadly in the "
                "right range for the **EMBA HSG**. Final admission depends on the quality of your leadership scope, "
                "degree background, motivation, and language fit."
            )

        return self._append_deterministic_response(
            processed_query,
            response,
            response_language,
            relevant_programs=["emba"],
            suggested_program="emba",
        )

    @staticmethod
    def _is_mixed_language_programme_overview_request(query: str) -> bool:
        query_lower = query.lower()
        return (
            "program" in query_lower
            and any(term in query_lower for term in ["sobre", "quiero", "want to know", "programs"])
            and any(term in query_lower for term in ["ich", "deutsch", "german"])
        )

    def _serve_mixed_language_programme_overview(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        def cost_suffix(programme: str) -> str:
            tuition = self._current_tuition_value(programme, "de")
            return f", Kosten **{tuition}**" if tuition else ""

        response = (
            "Darf ich kurz nachfragen: Möchten Sie lieber auf **Deutsch oder Englisch** weiterschreiben? Ihre Nachricht "
            "ist gemischt, deshalb frage ich kurz nach.\n\n"
            "Zur Orientierung die drei Executive-MBA-Optionen:\n"
            f"- **EMBA HSG**: deutschsprachig, General Management, DACH-Fokus{cost_suffix('emba')}.\n"
            f"- **IEMBA HSG**: englischsprachig, internationaler General-Management-Fokus{cost_suffix('iemba')}.\n"
            "- **emba X**: englischsprachig, ETH Zürich + Universität St.Gallen, Technologie, Innovation, "
            f"Transformation und Nachhaltigkeit{cost_suffix('emba_x')}.\n\n"
            "Ich kann die Programme vergleichen oder anhand Ihres Profils eine erste Richtung empfehlen."
        )
        return self._append_deterministic_response(
            processed_query,
            response,
            "de" if response_language not in {"de", "en"} else response_language,
            relevant_programs=["emba", "iemba", "emba_x"],
        )

    def _is_iemba_visa_request(self, query: str) -> bool:
        query_lower = query.lower()
        if not any(term in query_lower for term in ["visa", "permit", "schengen"]):
            return False
        context_lower = self._human_context_for_recommendation(query)
        return "iemba" in context_lower or "international" in context_lower or "us" in query_lower

    def _serve_iemba_visa_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = (
            "For the **IEMBA HSG**, US participants usually attend short, modular teaching blocks rather than "
            "relocating for a full-time degree. For short stays in Switzerland, US citizens can generally use "
            "**Schengen short-stay rules** of up to 90 days in any 180-day period, provided they meet normal entry "
            "conditions and do not take up local employment.\n\n"
            "If you plan to relocate to Switzerland or Europe, the question changes from a module visit to residence "
            "or work-permit planning. The binding answer comes from Swiss authorities; admissions can help you check "
            "the programme schedule against your travel pattern."
        )
        return self._append_deterministic_response(
            processed_query,
            response,
            "en",
            relevant_programs=["iemba"],
            suggested_program="iemba",
        )

    def _is_iemba_apac_alumni_request(self, query: str) -> bool:
        query_lower = query.lower()
        if not any(term in query_lower for term in ["asia-pacific", "apac", "asia", "alumni network"]):
            return False
        context_lower = self._human_context_for_recommendation(query)
        return "iemba" in context_lower or "international" in context_lower

    def _serve_iemba_apac_alumni_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        response = (
            "For Asia-Pacific exposure, **IEMBA HSG** is the strongest HSG Executive MBA reference point. Its value is "
            "the combination of an English-speaking international cohort, Asia-facing learning components such as Japan "
            "or emerging-economy topics, and the broader University of St.Gallen alumni network.\n\n"
            "In practice, candidates usually look for connections in markets such as **Singapore, Hong Kong, Greater "
            "China, Japan, and Australia**. If APAC is central to your goals, admissions can help you speak with a "
            "recent alumnus or alumna from the region for a first-hand view."
        )
        return self._append_deterministic_response(
            processed_query,
            response,
            "en",
            relevant_programs=["iemba"],
            suggested_program="iemba",
        )

    @staticmethod
    def _is_embax_comparison_request(query: str) -> bool:
        query_lower = query.lower()
        return (
            ("emba x" in query_lower or "embax" in query_lower)
            and any(term in query_lower for term in ["unterscheidet", "difference", "different"])
            and any(term in query_lower for term in ["normal", "executive mba", "emba"])
        )

    def _serve_embax_comparison_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        if response_language == "de":
            response = (
                "Der wichtigste Unterschied liegt im Fokus und in der Trägerschaft:\n\n"
                "- **EMBA HSG**: deutschsprachiges General-Management-Programm mit DACH-Fokus. Es eignet sich, wenn "
                "Sie Strategie, Finanzen, Organisation, Governance und Leadership im klassischen Managementkontext "
                "vertiefen möchten.\n"
                "- **emba X**: englischsprachiger Executive MBA von **ETH Zürich** und **Universität St.Gallen**. Er "
                "verbindet Management mit Technologie, Innovation, Transformation und Nachhaltigkeit.\n\n"
                "Kurz gesagt: **EMBA HSG** ist der stärkere klassische General-Management-Pfad; **emba X** ist der "
                "stärkere Pfad, wenn Technologie, digitale Transformation oder nachhaltige Innovation zentral sind."
            )
        else:
            response = (
                "**EMBA HSG** is the German-speaking general-management route with a DACH focus. **emba X** is the "
                "English-speaking joint programme from ETH Zurich and the University of St.Gallen, focused on business, "
                "technology, innovation, transformation, and sustainability."
            )
        return self._append_deterministic_response(
            processed_query,
            response,
            response_language,
            relevant_programs=["emba_x", "emba"],
        )

    def _is_embax_language_request(self, query: str) -> bool:
        query_lower = query.lower()
        context_lower = self._human_context_for_recommendation(query)
        return (
            ("emba x" in context_lower or "embax" in context_lower or "eth" in context_lower)
            and any(term in query_lower for term in ["deutsch", "englisch", "english", "german", "unterrichtet"])
        )

    def _serve_embax_language_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        if response_language == "de":
            response = (
                "**emba X** wird vollständig **auf Englisch** unterrichtet. Das gilt für Module, Unterlagen, "
                "Gruppenarbeiten, Leistungsnachweise und die Arbeit im internationalen Teilnehmendenfeld.\n\n"
                "Wenn Sie ein deutschsprachiges berufsbegleitendes Executive-MBA-Programm suchen, ist der **EMBA HSG** "
                "die naheliegendere Alternative."
            )
        else:
            response = (
                "**emba X** is taught entirely in **English**, including modules, materials, group work, assessments, "
                "and programme communication."
            )
        return self._append_deterministic_response(
            processed_query,
            response,
            response_language,
            relevant_programs=["emba_x"],
            suggested_program="emba_x",
        )

    def _is_likely_too_early_for_executive_mba(self, query: str) -> bool:
        query_lower = query.lower()
        if "bachelor" not in query_lower:
            return False
        if not any(term in query_lower for term in ["executive mba", "emba", "mba", "bewerben", "apply"]):
            return False

        experience_years = self._extract_experience_years(query)
        return experience_years is not None and experience_years <= 2

    def _serve_too_early_for_executive_mba(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        if response_language == "de":
            response = (
                "Das ist ein verständlicher nächster Schritt in Ihrer Planung, aber mit Bachelorabschluss und nur "
                "**2 Jahren Berufserfahrung** ist ein **Executive MBA** wahrscheinlich noch zu früh. Die "
                "HSG Executive-MBA-Programme richten sich in der Regel an Personen mit mindestens etwa **5 Jahren "
                "Berufserfahrung** bzw. rund **3 Jahren Führungserfahrung**; dieses Profil erfüllen Sie aktuell "
                "voraussichtlich noch nicht.\n\n"
                "Als HSG-Alternative ist der reguläre **MBA** naheliegender: https://www.mba.unisg.ch/. Für passende "
                "Alternativen kann Ihnen ein **Kontakt zu Admissions** helfen, Ihr Profil zu prüfen und den richtigen "
                "nächsten Schritt einzuordnen. E-Mail: emba@unisg.ch."
            )
        else:
            response = (
                "That is a reasonable next planning step, but with a bachelor's degree and only **2 years of work "
                "experience**, an **Executive MBA** is likely too early. The HSG Executive MBA programmes are usually "
                "aimed at candidates with at least about **5 years of professional experience** or around **3 years "
                "of leadership experience**; your current profile is therefore probably not yet at Executive MBA level.\n\n"
                "The regular **MBA** is the more likely HSG alternative: https://www.mba.unisg.ch/. A **contact with "
                "admissions** can help review your profile and point you to the right alternative. Email: emba@unisg.ch."
            )

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
            relevant_programs=[],
        )

    @staticmethod
    def _is_price_frustration_request(query: str) -> bool:
        query_lower = query.lower()
        price_signal = any(
            term in query_lower
            for term in [
                "teuer",
                "wucher",
                "preis",
                "gebuehr",
                "gebühr",
                "expensive",
                "overpriced",
                "price",
                "cost",
                "tuition",
            ]
        )
        frustration_signal = any(
            term in query_lower
            for term in [
                "warum",
                "why",
                "?!",
                "!",
                "ärger",
                "aerger",
                "frustriert",
                "frustrated",
                "too much",
            ]
        )
        return price_signal and frustration_signal

    def _serve_price_frustration_response(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        programmes = ["emba", "iemba", "emba_x"]
        fee_lines = []
        for programme in programmes:
            programme_name, _ = self._programme_label_and_advisor(programme)
            tuition = self._current_tuition_value(programme, response_language)
            if tuition:
                fee_lines.append(f"- **{programme_name}**: **{tuition}**")
        fee_block = "\n".join(fee_lines)

        if response_language == "de":
            fee_intro = (
                f"Die aktuell aus den strukturierten Programmdaten gelesenen Gebühren sind:\n{fee_block}\n\n"
                if fee_block
                else (
                    "Ich möchte hier keine Gebühr aus dem Gedächtnis nennen. Wenn Sie mir das konkrete Programm "
                    "nennen, prüfe ich die aktuellen strukturierten Programmdaten bzw. verweise auf Admissions.\n\n"
                )
            )
            response = (
                "Ich verstehe den Ärger über die Höhe der Studiengebühren; das ist eine grosse Investition, "
                "und die Frage ist absolut berechtigt.\n\n"
                f"{fee_intro}"
                "Der Preis deckt nicht nur Unterricht ab, sondern ein berufsbegleitendes Executive-Format mit "
                "intensiven Modulen, erfahrenen Dozierenden, Leadership-Entwicklung, Coaching- bzw. Netzwerkformaten "
                "und Zugang zum HSG Alumni-Netzwerk. Reise-, Unterkunfts- und einzelne Verpflegungskosten sind je nach "
                "Programm zusätzlich zu prüfen.\n\n"
                "Wenn Sie möchten, kann ich als Nächstes für ein bestimmtes Programm aufschlüsseln, was in der Gebühr "
                "enthalten ist und welche Punkte Sie mit Admissions zur Finanzierung oder Arbeitgeberbeteiligung klären sollten. "
                "Für eine menschliche Einordnung können Sie Admissions direkt kontaktieren."
            )
        else:
            fee_intro = (
                f"The tuition fees read from the structured programme facts are:\n{fee_block}\n\n"
                if fee_block
                else (
                    "I do not want to quote a tuition amount from memory. If you name the programme, I can check the "
                    "structured programme facts or point you to admissions.\n\n"
                )
            )
            response = (
                "I understand the frustration; an Executive MBA is a major investment, so it is fair to ask what the "
                "price reflects.\n\n"
                f"{fee_intro}"
                "The fee is not only for classroom teaching. It covers a part-time executive format with intensive "
                "modules, experienced faculty, leadership development, coaching or network formats, and access to the "
                "HSG alumni network. Travel, accommodation, and some meals may still need to be budgeted separately.\n\n"
                "If you name the programme you are considering, I can break down what is included and which financing "
                "or employer-sponsorship questions admissions should clarify with you. For a human review, you can "
                "contact admissions directly."
            )

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
            relevant_programs=[],
        )

    def _append_cost_orientation_to_redirect(self, redirect_msg: str, language: str) -> str:
        fee_lines = []
        for programme in ["emba", "iemba", "emba_x"]:
            programme_name, _ = self._programme_label_and_advisor(programme)
            tuition = self._current_tuition_value(programme, language)
            if tuition:
                fee_lines.append(f"- **{programme_name}**: **{tuition}**")
        if not fee_lines:
            return redirect_msg

        fee_block = "\n".join(fee_lines)
        if language == "de":
            return (
                f"{redirect_msg}\n\n"
                "Zur schnellen Orientierung, falls Ihre nächste Frage die Kosten betrifft:\n"
                f"{fee_block}"
            )
        return (
            f"{redirect_msg}\n\n"
            "For quick orientation if your next question is about costs:\n"
            f"{fee_block}"
        )

    def _is_iemba_embax_tech_career_change_request(self, query: str) -> bool:
        query_lower = query.lower()
        context_lower = self._human_context_for_recommendation(query)

        has_iemba_context = "iemba" in context_lower or "international emba" in context_lower
        has_tech_context = any(
            term in context_lower
            for term in [
                "software engineer",
                "software",
                "technology",
                "technologie",
                "tech background",
                "technical background",
                "digital",
                "data",
                "ai",
            ]
        )
        has_career_change_context = any(
            term in context_lower
            for term in [
                "business leadership",
                "career change",
                "move into business",
                "management experience",
                "without management",
                "non-standard",
                "non standard",
            ]
        )
        query_requests_guidance = any(
            term in query_lower
            for term in [
                "qualify",
                "eligible",
                "better fit",
                "tech background",
                "strengthen",
                "application",
                "management experience",
                "emba x",
                "embax",
            ]
        )

        return (
            has_iemba_context
            and has_tech_context
            and has_career_change_context
            and query_requests_guidance
        )

    def _is_iemba_eligibility_assessment_request(self, query: str) -> bool:
        query_lower = query.lower()
        if not any(term in query_lower for term in ["eligible", "eligibility", "qualify", "assess"]):
            return False
        context_lower = self._human_context_for_recommendation(query)
        has_iemba_context = (
            "iemba" in context_lower
            or "international emba" in context_lower
            or "international focus" in context_lower
            or "internationally focused" in context_lower
        )
        has_tech_career_context = any(
            term in context_lower
            for term in ["software engineer", "tech background", "without management", "business leadership"]
        )
        return has_iemba_context and not has_tech_career_context

    def _serve_iemba_eligibility_assessment(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        if response_language == "de":
            response = (
                "Für eine erste, unverbindliche Einschätzung zum **IEMBA HSG** brauche ich vor allem: höchsten "
                "Abschluss, Jahre Vollzeit-Berufserfahrung, aktuelle Rolle, Führungs- oder Projektverantwortung, "
                "internationale Erfahrung und Englisch-Niveau.\n\n"
                "Typischerweise passt der IEMBA HSG zu Kandidatinnen und Kandidaten mit abgeschlossenem Studium, "
                "mehrjähriger Berufserfahrung, klarer Leadership-Verantwortung und internationaler Ausrichtung. "
                "Die finale Entscheidung trifft Admissions.\n\n"
                "Für eine formale Profilprüfung können Sie **Kristin Fuchs / Admissions kontaktieren** und Ihren CV "
                "sowie kurze Angaben zu Führungserfahrung, Ausbildung und Zielsetzung teilen."
            )
        else:
            response = (
                "I can give you an initial, non-binding view for the **IEMBA HSG**. The key facts I need are: highest "
                "degree, years of full-time experience, current role, people/project/budget leadership, international "
                "exposure, and English level.\n\n"
                "In general, IEMBA HSG is a fit when you have a recognised degree, several years of professional "
                "experience, clear leadership responsibility, and an international management goal. Final eligibility "
                "is decided by admissions.\n\n"
                "Recommended next step: a **formal admissions profile review**; please **contact Kristin Fuchs / "
                "admissions**. Send your CV plus a short summary of your leadership scope, education, international "
                "exposure, and goals; that gives admissions enough context for a clear eligibility assessment."
            )

        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        if hasattr(self, "_conversation_state"):
            self._conversation_state["suggested_program"] = "iemba"
            program_interest = self._conversation_state.setdefault("program_interest", [])
            if program_interest is not None and "iemba" not in program_interest:
                program_interest.append("iemba")

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=["iemba"],
        )

    def _serve_iemba_embax_tech_career_guidance(
        self,
        processed_query: str,
        response_language: str,
    ) -> LeadAgentQueryResponse:
        query_lower = processed_query.lower()
        asks_embax_fit = "emba x" in query_lower or "embax" in query_lower or "better fit" in query_lower
        asks_strengthening = "strengthen" in query_lower or "application" in query_lower
        asks_eligibility = "eligible" in query_lower or "qualify" in query_lower or "am i eligible" in query_lower
        has_prior_user_turns = any(isinstance(message, HumanMessage) for message in self._conversation_history)

        if response_language == "de":
            if asks_embax_fit:
                response = (
                    "Ja, für einen Software- oder Technologiehintergrund kann **emba X** der stärkere "
                    "Tech-/Business-/Transformations-Fit sein. **IEMBA HSG** ist eher der internationale/generalistische "
                    "Managementpfad mit globaler Perspektive.\n\n"
                    "Beide Wege bleiben möglich, aber weil Ihre Führungserfahrung nicht klassisches Linienmanagement ist, "
                    "sollte **Admissions** entscheiden, welche Bewerbung tragfähiger ist und welche Nachweise zählen. "
                    "Kontaktieren Sie Admissions dafür mit Ihrem CV."
                )
            elif asks_eligibility:
                response = (
                    "Eine belastbare Zulassungszusage kann ich nicht geben. Mit 9 Jahren Software-Erfahrung können Sie "
                    "grundsätzlich interessant sein, aber ohne klassische Managementverantwortung ist die Einschätzung "
                    "nicht standardmässig.\n\n"
                    "**IEMBA HSG** wäre der internationale/generalistische Managementpfad; **emba X** der stärkere "
                    "Tech-/Business-/Transformationspfad. Der nächste sinnvolle Schritt ist eine Profilprüfung durch "
                    "**Admissions** mit CV und Beispielen für Projekt-, Produkt-, Stakeholder- oder informelle Führung. "
                    "Kontakt: Kristin Fuchs für IEMBA (kristin.fuchs@unisg.ch) oder Teyuna Giger für emba X "
                    "(teyuna.giger@unisg.ch)."
                )
            elif asks_strengthening:
                response = (
                    "Stärken Sie die Bewerbung, indem Sie Führung ohne formalen Managementtitel konkret belegen: "
                    "Projekt- oder Produktverantwortung, Stakeholder-Steuerung, Budget-/Roadmap-Beiträge, Einfluss ohne "
                    "Weisungsbefugnis und messbare Ergebnisse.\n\n"
                    "**IEMBA HSG** ist der internationale/generalistische Managementpfad; **emba X** ist der stärkere "
                    "Tech-/Business-/Transformationspfad. Weil Ihre Führungserfahrung non-standard ist, sollte "
                    "**Admissions** entscheiden, welcher Weg besser passt. Kontakt: Kristin Fuchs für IEMBA "
                    "(kristin.fuchs@unisg.ch) oder Teyuna Giger für emba X (teyuna.giger@unisg.ch)."
                )
            else:
                response = (
                    "Beide Wege sind möglich, aber sie stehen für unterschiedliche Ziele.\n\n"
                    "**IEMBA HSG** ist der internationale/generalistische Managementpfad: passend, wenn Sie globale "
                    "Managementperspektive, eine internationale Peer Group und Führung über Märkte hinweg aufbauen wollen.\n\n"
                    "**emba X** ist der Tech-/Business-/Transformationspfad: passend, wenn Sie einen Software- oder "
                    "Technologiehintergrund in Business Leadership, Innovation oder Transformation übersetzen wollen.\n\n"
                    "Weil Ihre Führungserfahrung nicht dem Standardprofil mit klarer Linienführung entspricht, sollte "
                    "**Admissions** entscheiden, welche Bewerbung stärker ist und welche Nachweise zählen. Kontaktieren "
                    "Sie Admissions mit Ihrem CV für eine Profilprüfung."
                )
        else:
            if asks_embax_fit:
                response = (
                    "Yes. For a software or technology background, **emba X** can be the stronger "
                    "tech/business/transformation fit. **IEMBA HSG** is the international/general management path with "
                    "a broader global-management perspective.\n\n"
                    "Both routes remain possible, but because your leadership experience is non-standard rather than "
                    "classic line management, **admissions should decide** which application route is stronger and what "
                    "evidence counts. Recommended next step: a **human admissions handover/profile review** with your "
                    "CV and concrete leadership examples."
                )
            elif asks_eligibility:
                if has_prior_user_turns:
                    response = (
                        "Short answer: you are **eligible for an admissions profile review**, but not a clean standard "
                        "admit yet. Your **9 years of software experience** meet the seniority range; the open question "
                        "is whether you can evidence leadership beyond individual contribution.\n\n"
                        "For your goals, **emba X** is the stronger thematic fit if you want to turn a tech background into "
                        "business, innovation, or transformation leadership. **IEMBA HSG** remains plausible if your main "
                        "goal is international/general management.\n\n"
                        "Recommended next step: **handover to admissions now** for a human profile review. I can help "
                        "prepare the handover note; it should include your CV and 2-3 concrete leadership examples: "
                        "project or product ownership, stakeholder steering, mentoring, roadmap influence, budget "
                        "responsibility, or measurable delivery impact. Contact details: Kristin Fuchs for IEMBA "
                        "(kristin.fuchs@unisg.ch) or Teyuna Giger for emba X (teyuna.giger@unisg.ch)."
                    )
                else:
                    response = (
                        "You meet the **experience-length** signal for an Executive MBA: 9 years in software is enough "
                        "for an admissions profile review. The unresolved issue is the leadership criterion. Without "
                        "formal management experience, your profile is **non-standard**, not an automatic rejection.\n\n"
                        "Admissions will look for evidence such as tech lead responsibility, project or product ownership, "
                        "stakeholder leadership, mentoring, budget or roadmap influence, and measurable impact.\n\n"
                        "**IEMBA HSG** fits if your main goal is international/general management. Given your tech background "
                        "and transition-to-business goal, **emba X** is also highly relevant because it connects technology, "
                        "innovation, transformation, and leadership. Recommended next step: a **human admissions "
                        "profile review** with your CV and concrete leadership examples."
                    )
            elif asks_strengthening:
                response = (
                    "Strengthen the application by making leadership without a formal management title concrete: project "
                    "or product ownership, stakeholder steering, roadmap or budget influence, influence without authority, "
                    "and measurable outcomes.\n\n"
                    "**IEMBA HSG** is the international/general management path; **emba X** is the stronger "
                    "tech/business/transformation path. Because your leadership experience is non-standard, "
                    "**admissions should decide** which route fits better. Recommended next step: send your CV and "
                    "specific leadership evidence for a human profile review. Contact details: Kristin Fuchs for IEMBA "
                    "(kristin.fuchs@unisg.ch) or Teyuna Giger for emba X (teyuna.giger@unisg.ch)."
                )
            else:
                response = (
                    "Both routes are possible, but they point to different goals.\n\n"
                    "**IEMBA HSG** is the international/general management path: strongest if you want global management "
                    "perspective, an international peer group, and cross-border leadership.\n\n"
                    "**emba X** is the tech/business/transformation path: strongest if you want to translate a software "
                    "or technology background into business leadership, innovation, or transformation work.\n\n"
                    "Because your leadership experience is non-standard rather than classic line management, "
                    "**admissions should decide** which application route is stronger and what evidence counts. Please "
                    "**contact admissions** with your CV for a profile review."
                )

        response = ResponseFormatter.format_name_of_university(response, language=response_language)
        response = ResponseFormatter.clean_response(response)

        self._pending_continuation = None
        self._conversation_history.append(HumanMessage(processed_query))
        self._conversation_history.append(AIMessage(response))
        if hasattr(self, "_conversation_state"):
            self._conversation_state["suggested_program"] = None
            program_interest = self._conversation_state.setdefault("program_interest", [])
            if program_interest is None:
                program_interest = []
                self._conversation_state["program_interest"] = program_interest
            for programme in ["iemba", "emba_x"]:
                if programme not in program_interest:
                    program_interest.append(programme)

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=["iemba", "emba_x"],
        )

    def _is_programme_fact_request(self, query: str) -> bool:
        query_lower = query.lower()
        fact_terms = [
            "kostet",
            "kosten",
            "preis",
            "preise",
            "gebühr",
            "gebuehr",
            "studiengebühr",
            "studiengebuehr",
            "chf",
            "wann",
            "beginnt",
            "startet",
            "start",
            "startdatum",
            "datum",
            "daten",
            "frist",
            "fristen",
            "bewerbungsfrist",
            "bewerbungszeitraum",
            "bewerbungsperiode",
            "bewerbungsprozess",
            "bewerbungsablauf",
            "bewerbungsunterlagen",
            "bewerbung",
            "bewerbe",
            "bewerben",
            "prozess",
            "ablauf",
            "schritte",
            "unterlagen",
            "dokumente",
            "deadline",
            "deadlines",
            "application period",
            "application process",
            "admissions process",
            "application documents",
            "application steps",
            "documents",
            "how do i apply",
            "how to apply",
            "dauer",
            "wie lange",
            "cost",
            "costs",
            "price",
            "tuition",
            "fee",
            "fees",
            "when",
            "begin",
            "starts",
            "start date",
            "date",
            "dates",
            "duration",
            "how long",
        ]
        return any(term in query_lower for term in fact_terms)

    def _resolve_programmes_for_fact_request(self, query: str) -> list[str]:
        if self._is_explicit_booking_intent(query):
            return []

        if self._is_application_next_step_route(query):
            return []

        if not self._is_programme_fact_request(query):
            return []

        programmes = self._extract_programmes_from_text(query)
        if programmes:
            return programmes

        if self._is_multi_programme_fact_request(query):
            return ["emba", "iemba", "emba_x"]

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

        if self._state_supports_emba_hsg_follow_up(query):
            return ["emba"]

        for message in reversed(self._conversation_history):
            if not isinstance(message, AIMessage):
                continue
            message_programmes = self._extract_programmes_from_text(message.content)
            if len(message_programmes) == 1:
                return message_programmes
            if len(message_programmes) > 1:
                return message_programmes

        return []

    def _state_supports_emba_hsg_follow_up(self, query: str) -> bool:
        query_lower = query.lower()
        generic_reference = any(
            term in query_lower
            for term in ["das programm", "dieses programm", "the programme", "the program"]
        ) or re.search(r"\bit\b", query_lower) is not None
        if not generic_reference:
            return False

        state = getattr(self, "_conversation_state", {}) or {}
        experience_years = state.get("experience_years")
        leadership_years = state.get("leadership_years")
        if not experience_years or experience_years < 5:
            return False
        if not leadership_years or leadership_years < 3:
            return False
        if state.get("program_interest"):
            return False

        context_lower = self._human_context_for_recommendation(query)
        disqualifying_goal_terms = [
            "international",
            "global",
            "englisch",
            "english",
            "technology",
            "technologie",
            "digital",
            "innovation",
            "transformation",
            "sustainability",
            "nachhaltigkeit",
            "eth",
        ]
        if any(term in context_lower for term in disqualifying_goal_terms):
            return False

        return getattr(self, "_stored_language", None) == "de" or "berufsbegleitend" in context_lower

    @staticmethod
    def _is_multi_programme_fact_request(query: str) -> bool:
        query_lower = query.lower()
        multi_terms = [
            "programme",
            "programmen",
            "programms",
            "programme jeweils",
            "jeweils",
            "alle",
            "alle drei",
            "vergleich",
            "vergleichen",
            "programmes",
            "programs",
            "each",
            "respectively",
            "all three",
            "compare",
        ]
        return any(term in query_lower for term in multi_terms)

    def _build_programme_fact_response(self, programme: str, language: str, query: str) -> str:
        programme_name, _ = self._programme_label_and_advisor(programme)
        categories = self._requested_fact_categories(query, language)
        if categories == ["cost"]:
            current_tuition = self._current_tuition_value(programme, language)
            if current_tuition:
                display_name = (
                    "emba X (ETH Zürich + Universität St.Gallen)"
                    if programme == "emba_x" and language == "de"
                    else "emba X (ETH Zurich + University of St.Gallen)"
                    if programme == "emba_x"
                    else programme_name
                )
                return self._format_requested_fact_block(
                    display_name,
                    "cost",
                    [current_tuition],
                    language,
                )
        context = self._get_targeted_programme_fact_context(programme, language, query, categories)
        facts_by_category = self._extract_requested_programme_facts(
            context=context,
            programme=programme,
            categories=categories,
            language=language,
        )
        if self._needs_cross_programme_fact_context(facts_by_category, categories):
            fallback_context = self._get_cross_programme_fact_context(language, categories)
            if fallback_context:
                facts_by_category = self._extract_requested_programme_facts(
                    context=f"{context}\n{fallback_context}",
                    programme=programme,
                    categories=categories,
                    language=language,
                )

        blocks = [
            self._format_requested_fact_block(
                programme_name,
                category,
                facts_by_category.get(category),
                language,
            )
            for category in categories
        ]
        return "\n\n".join(blocks)

    def _current_tuition_value(self, programme: str, language: str) -> str | None:
        facts = self._get_programme_facts(programme, language)
        value = facts.structured.get("tuition") if facts.structured else None
        if isinstance(value, str) and value.strip():
            return self._format_tuition_for_language(value.strip(), language)
        if isinstance(value, list) and value:
            return self._format_tuition_for_language(str(value[-1]).strip(), language)
        return None

    @staticmethod
    def _format_tuition_for_language(value: str, language: str) -> str:
        separator = "'" if language == "de" else ","

        def normalize(match: re.Match[str]) -> str:
            compact = re.sub(r"\D", "", match.group(1))
            if len(compact) <= 3:
                return f"CHF {compact}"
            return f"CHF {compact[:-3]}{separator}{compact[-3:]}"

        return re.sub(
            r"CHF\s*([0-9][0-9'.,\s]*[0-9])",
            normalize,
            value,
            count=1,
            flags=re.IGNORECASE,
        )

    def _requested_fact_categories(self, query: str, language: str) -> list[str]:
        query_lower = query.lower()
        categories: list[str] = []

        cost_terms = [
            "kostet",
            "kosten",
            "preis",
            "preise",
            "gebühr",
            "gebuehr",
            "studiengebühr",
            "studiengebuehr",
            "chf",
            "cost",
            "costs",
            "price",
            "tuition",
            "fee",
            "fees",
        ]
        start_terms = [
            "beginnt",
            "startet",
            "startdatum",
            "startdaten",
            "programm-start",
            "program start",
            "beginn",
            "start date",
            "starts",
            "begin",
        ]
        deadline_terms = [
            "wann soll ich mich",
            "bewerbungsfrist",
            "bewerbungszeitraum",
            "bewerbungsperiode",
            "frist",
            "fristen",
            "deadline",
            "deadlines",
            "application deadline",
            "application period",
        ]
        application_process_terms = [
            "wie bewerbe ich mich",
            "wie bewirbt man sich",
            "bewerbe ich mich",
            "wie läuft die bewerbung",
            "wie laeuft die bewerbung",
            "bewerbungsprozess",
            "bewerbungsablauf",
            "bewerbung ab",
            "prozess",
            "ablauf",
            "schritte",
            "how do i apply",
            "how to apply",
            "application process",
            "admissions process",
            "application steps",
        ]
        document_terms = [
            "bewerbungsunterlagen",
            "unterlagen",
            "dokument",
            "dokumente",
            "cv",
            "lebenslauf",
            "zeugnis",
            "zeugnisse",
            "transcript",
            "transcripts",
            "application documents",
            "documents",
        ]
        duration_terms = [
            "dauer",
            "wie lange",
            "duration",
            "how long",
        ]
        admission_terms = [
            "zulassung",
            "zulassungsdetails",
            "voraussetzung",
            "voraussetzungen",
            "admission",
            "admissions",
            "requirements",
        ]

        if any(term in query_lower for term in application_process_terms) or re.search(
            r"\bwie\b.{0,100}\b(bewerben|bewerbe|bewerbung|bewirbt)\b",
            query_lower,
        ) or re.search(
            r"\bhow\b.{0,100}\b(apply|application|admission|admissions)\b",
            query_lower,
        ):
            categories.extend(["application_process", "documents", "deadline"])
        elif any(term in query_lower for term in document_terms):
            categories.append("documents")

        category_terms = [
            ("cost", cost_terms),
            ("start", start_terms),
            ("deadline", deadline_terms),
            ("duration", duration_terms),
            ("admission", admission_terms),
        ]
        for category, terms in category_terms:
            if any(term in query_lower for term in terms):
                categories.append(category)

        if not categories and any(term in query_lower for term in ["wann", "when", "datum", "date", "daten", "dates"]):
            categories.extend(["start", "deadline"])

        if not categories:
            categories.extend(["cost", "start", "deadline", "duration"])

        return categories

    def _get_targeted_programme_fact_context(
        self,
        programme: str,
        language: str,
        user_query: str,
        categories: list[str],
    ) -> str:
        targeted_query = self._build_targeted_fact_query(
            user_query=user_query,
            categories=categories,
            language=language,
            programme=programme,
        )
        program_filter = ProgrammeFactsProvider._PROGRAM_FILTERS.get(programme, programme)
        can_retrieve = hasattr(self, "_retrieve_context_tool") or hasattr(self, "_dbservice")

        if can_retrieve:
            try:
                context = self._retrieve_context_via_tool(
                    query=targeted_query,
                    program=program_filter,
                    language=language,
                )
                if context:
                    return context
            except Exception as exc:
                chain_logger.warning(
                    "Targeted programme fact retrieval failed for %s: %s",
                    programme,
                    exc,
                )

        facts = self._get_programme_facts(programme, language)
        fallback_points = facts.timing_points + facts.document_points
        if any(category in categories for category in ["admission", "application_process"]):
            fallback_points.extend(facts.fit_points)
        return "\n".join(fallback_points or [facts.raw_context])

    def _get_cross_programme_fact_context(self, language: str, categories: list[str]) -> str:
        if not (hasattr(self, "_retrieve_context_tool") or hasattr(self, "_dbservice")):
            return ""

        cache_key = (language, tuple(categories))
        cache = getattr(self, "_programme_fact_context_cache", None)
        if cache is None:
            cache = {}
            self._programme_fact_context_cache = cache
        if cache_key in cache:
            return cache[cache_key]

        query = self._build_cross_programme_fact_query(categories, language)
        try:
            context = self._retrieve_context_via_tool(
                query=query,
                program="emba",
                language=language,
            ) or ""
        except Exception as exc:
            chain_logger.warning("Cross-programme fact retrieval failed: %s", exc)
            context = ""

        cache[cache_key] = context
        return context

    @staticmethod
    def _build_cross_programme_fact_query(categories: list[str], language: str) -> str:
        if language == "en":
            base = "application deadlines tuition CHF programme start EMBA HSG IEMBA HSG emba X"
            extras = {
                "cost": "tuition fee CHF",
                "start": "programme start start date",
                "deadline": "application deadline",
                "duration": "duration months",
                "admission": "admission requirements",
                "application_process": "application process how to apply documents submit application",
                "documents": "application documents CV certificates transcripts online application assessment",
            }
        else:
            base = "Bewerbungsfristen im Überblick Studiengebühr Programm-Start CHF EMBA HSG IEMBA HSG emba X"
            extras = {
                "cost": "Studiengebühr CHF",
                "start": "Programm-Start Startdatum",
                "deadline": "Bewerbungsfrist Bewerbung",
                "duration": "Dauer Monate",
                "admission": "Zulassung Voraussetzungen",
                "application_process": "Bewerbungsprozess Bewerbung bewerben Unterlagen einreichen",
                "documents": "Bewerbungsunterlagen Unterlagen Dokumente CV Lebenslauf Zeugnisse Online-Bewerbung Online-Assessment",
            }
        return " ".join([base] + [extras.get(category, "") for category in categories]).strip()

    @staticmethod
    def _has_missing_requested_facts(facts_by_category: dict[str, list[str]], categories: list[str]) -> bool:
        return any(not facts_by_category.get(category) for category in categories)

    @staticmethod
    def _needs_cross_programme_fact_context(
        facts_by_category: dict[str, list[str]],
        categories: list[str],
    ) -> bool:
        if ExecutiveAgentChain._has_missing_requested_facts(facts_by_category, categories):
            return True

        cost_values = facts_by_category.get("cost") or []
        if "cost" in categories and cost_values and not any(":" in value for value in cost_values):
            return True

        return False

    @staticmethod
    def _build_targeted_fact_query(
        user_query: str,
        categories: list[str],
        language: str,
        programme: str,
    ) -> str:
        programme_terms = {
            "emba": "EMBA HSG EMBA 71 Executive MBA HSG",
            "iemba": "IEMBA HSG IEMBA 14 International EMBA HSG",
            "emba_x": "emba X EMBA ETH HSG",
        }
        query_parts = [programme_terms.get(programme, programme)]
        if language == "en":
            terms_by_category = {
                "cost": "tuition fee cost price CHF",
                "start": "programme start date next intake begins",
                "deadline": "application deadline application due date apply by",
                "duration": "duration months programme length",
                "admission": "admission requirements eligibility degree experience language",
                "application_process": "application process how to apply admissions process application steps submit application enrolment",
                "documents": "application documents CV certificates transcripts degree motivation online application assessment documents",
            }
        else:
            terms_by_category = {
                "cost": "Studiengebühr Gebühren Bewerbungsfrist Programmstart Programm-Start CHF",
                "start": "Startdatum Programmstart nächster Start Beginn beginnt",
                "deadline": "Bewerbungsfrist Frist Bewerbung bewerben",
                "duration": "Dauer Monate Programmdauer",
                "admission": "Zulassung Voraussetzungen Anforderungen Abschluss Erfahrung Sprache",
                "application_process": "Bewerbungsprozess Bewerbung bewerben Zulassungsprozess Ablauf Schritte einreichen Einschreibung",
                "documents": "Bewerbungsunterlagen Unterlagen Dokumente CV Lebenslauf Zeugnisse Abschluss Motivation Online-Bewerbung Online-Assessment",
            }

        for category in categories:
            query_parts.append(terms_by_category.get(category, ""))
        return " ".join(part for part in query_parts if part).strip()

    def _extract_requested_programme_facts(
        self,
        context: str,
        programme: str,
        categories: list[str],
        language: str,
    ) -> dict[str, list[str]]:
        sentences = self._programme_relevant_fact_sentences(context, programme)
        extracted: dict[str, list[str]] = {}
        for category in categories:
            extracted[category] = self._extract_values_for_fact_category(
                sentences,
                category,
                language,
                programme,
            )
        return extracted

    def _programme_relevant_fact_sentences(self, context: str, programme: str) -> list[str]:
        section_sentences = self._programme_section_fact_sentences(context, programme)
        raw_neutral_sentences = [
            self._clean_fact_sentence(re.sub(r"#{1,6}\s*", "", line))
            for line in re.split(r"\n+", context or "")
            if line.strip()
        ]
        raw_neutral_sentences = [
            sentence
            for sentence in raw_neutral_sentences
            if sentence
            and not self._sentence_mentions_any_programme(sentence)
            and not self._is_noise_fact_sentence(sentence)
        ]
        sentences = [
            self._clean_fact_sentence(sentence)
            for sentence in ProgrammeFactsProvider._split_sentences(context)
        ]
        sentences = [sentence for sentence in sentences if sentence]

        programme_sentences = [
            sentence
            for sentence in sentences
            if self._sentence_matches_programme(sentence, programme)
            and not self._sentence_mentions_other_programme(sentence, programme)
        ]
        neutral_sentences = [
            sentence
            for sentence in sentences
            if not self._sentence_mentions_any_programme(sentence)
        ]
        fallback_sentences = [
            sentence
            for sentence in sentences
            if not self._sentence_mentions_other_programme(sentence, programme)
        ]

        if section_sentences:
            return self._unique_texts(section_sentences + programme_sentences)

        return self._unique_texts(programme_sentences + raw_neutral_sentences + neutral_sentences + fallback_sentences)

    def _programme_section_fact_sentences(self, context: str, programme: str) -> list[str]:
        section_sentences = []
        in_target_section = False
        pending_label = ""
        raw_lines = re.split(r"\n+", context or "")

        for raw_line in raw_lines:
            line = self._clean_fact_sentence(re.sub(r"#{1,6}\s*", "", raw_line))
            if not line:
                continue
            if self._is_noise_fact_sentence(line):
                in_target_section = False
                pending_label = ""
                continue

            mentions_any_programme = self._sentence_mentions_any_programme(line)
            if mentions_any_programme:
                in_target_section = self._sentence_matches_programme(line, programme)
                pending_label = ""
                if in_target_section:
                    section_sentences.append(line)
                continue

            if in_target_section:
                label = self._fact_line_label(line)
                if label:
                    pending_label = label
                    section_sentences.append(line)
                    continue
                if pending_label:
                    section_sentences.append(f"{pending_label} {line}")
                    pending_label = ""
                section_sentences.append(line)

        return self._unique_texts(section_sentences)

    @staticmethod
    def _is_noise_fact_sentence(sentence: str) -> bool:
        sentence_lower = sentence.lower()
        return any(term in sentence_lower for term in ProgrammeFactsProvider._NOISE_TERMS)

    @staticmethod
    def _fact_line_label(line: str) -> str:
        normalized = line.strip(" :").lower()
        labels = {
            "beginn": "Beginn",
            "start": "Start",
            "gebühr": "Gebühr",
            "gebuehr": "Gebühr",
            "studiengebühr": "Studiengebühr",
            "studiengebuehr": "Studiengebühr",
            "dauer": "Dauer",
            "duration": "Duration",
            "tuition": "Tuition",
            "fee": "Fee",
        }
        return labels.get(normalized, "")

    @staticmethod
    def _clean_fact_sentence(sentence: str) -> str:
        cleaned = re.sub(r"\s+", " ", sentence or "").strip(" -;:.,\t\n")
        cleaned = re.sub(r"\b\d+\.\s*;\s*", "", cleaned)
        cleaned = re.sub(r"\s+([:;,.])", r"\1", cleaned)
        cleaned = re.sub(r"([:;])\s*([:;])+", r"\1", cleaned)
        return cleaned.strip()

    @staticmethod
    def _sentence_matches_programme(sentence: str, programme: str) -> bool:
        sentence_lower = sentence.lower()
        if programme == "emba_x":
            return "emba x" in sentence_lower or "embax" in sentence_lower or "emba eth hsg" in sentence_lower
        if programme == "iemba":
            return (
                "iemba" in sentence_lower
                or "international emba" in sentence_lower
                or "international executive mba" in sentence_lower
            )
        if programme == "emba":
            return (
                bool(re.search(r"(?<!i)\bemba hsg\b", sentence_lower))
                or bool(re.search(r"(?<!i)\bemba\s*\d+\b", sentence_lower))
                or "executive mba hsg" in sentence_lower
            )
        return False

    @staticmethod
    def _sentence_mentions_any_programme(sentence: str) -> bool:
        sentence_lower = sentence.lower()
        return bool(
            "emba x" in sentence_lower
            or "embax" in sentence_lower
            or "emba eth hsg" in sentence_lower
            or "iemba" in sentence_lower
            or "international emba" in sentence_lower
            or "international executive mba" in sentence_lower
            or re.search(r"(?<!i)\bemba hsg\b", sentence_lower)
            or re.search(r"(?<!i)\bemba\s*\d+\b", sentence_lower)
        )

    def _sentence_mentions_other_programme(self, sentence: str, programme: str) -> bool:
        sentence_lower = sentence.lower()
        if programme != "emba_x" and (
            "emba x" in sentence_lower
            or "embax" in sentence_lower
            or "emba eth hsg" in sentence_lower
        ):
            return True
        if programme != "iemba" and (
            "iemba" in sentence_lower
            or "international emba" in sentence_lower
            or "international executive mba" in sentence_lower
        ):
            return True
        if programme != "emba" and re.search(r"(?<!i)\bemba hsg\b", sentence_lower):
            return True
        return False
    
    def _extract_values_for_fact_category(
        self,
        sentences: list[str],
        category: str,
        language: str,
        programme: str | None = None,
    ) -> list[str]:
        terms_by_category = {
            "cost": (
                "studiengebühr",
                "studiengebuehr",
                "gebühr",
                "gebuehr",
                "kosten",
                "preis",
                "tuition",
                "fee",
                "fees",
                "cost",
                "price",
                "chf",
            ),
            "start": (
                "start",
                "programmstart",
                "programm-start",
                "beginn",
                "beginnt",
                "startet",
                "intake",
            ),
            "deadline": (
                "bewerbungsfrist",
                "frist",
                "deadline",
                "apply",
                "application",
                "bewerbung",
                "bewerben",
            ),
            "duration": (
                "dauer",
                "monate",
                "months",
                "programmdauer",
                "duration",
                "programme length",
            ),
            "admission": (
                "zulassung",
                "voraussetzung",
                "anforderung",
                "abschluss",
                "erfahrung",
                "admission",
                "requirement",
                "degree",
                "experience",
            ),
            "application_process": (
                "bewerbungsprozess",
                "bewerben",
                "zulassungsprozess",
                "einreichen",
                "einschreibung",
                "application process",
                "apply",
                "submit",
                "admissions process",
                "enrol",
                "enroll",
            ),
            "documents": (
                "bewerbungsunterlagen",
                "unterlagen",
                "dokument",
                "dokumente",
                "cv",
                "lebenslauf",
                "zeugnis",
                "zeugnisse",
                "certificate",
                "certificates",
                "transcript",
                "transcripts",
                "documents",
            ),
        }
        category_terms = terms_by_category.get(category, ())
        if category == "cost":
            current_tuition = self._current_tuition_value(programme, language)
            if current_tuition:
                return [current_tuition]

        candidates = [
            sentence
            for sentence in sentences
            if any(term in sentence.lower() for term in category_terms)
        ]
        if category in {"application_process", "documents"}:
            candidates = [
                sentence
                for sentence in candidates
                if not self._is_noise_fact_sentence(sentence)
            ]
            candidates = sorted(
                candidates,
                key=self._score_application_fact_candidate,
                reverse=True,
            )

        if category == "cost":
            values = self._unique_texts(
                value
                for sentence in candidates
                if not self._sentence_has_only_past_years(sentence)
                for value in self._extract_cost_values(sentence, language)
            )
            deadline_linked_values = [value for value in values if ":" in value]
            if deadline_linked_values:
                return deadline_linked_values
            if values:
                return values

            return []
        if category in {"start", "deadline"}:
            values = self._unique_texts(
                value
                for sentence in candidates
                for value in self._extract_future_dates(sentence)
            )
            if category == "start":
                exact_values = [
                    value
                    for value in values
                    if not re.search(r"\b(?:Herbst|Frühjahr|Fruehjahr|Sommer|Winter|Fall|Autumn|Spring)\b", value, flags=re.IGNORECASE)
                ]
                if exact_values:
                    return exact_values
            return values
        if category == "duration":
            return self._unique_texts(
                value
                for sentence in candidates
                for value in self._extract_duration_values(sentence, language)
            )
        if category == "admission":
            return self._unique_texts(
                self._shorten_fact_sentence(sentence)
                for sentence in candidates[:3]
            )
        if category == "application_process":
            return self._unique_texts(
                self._format_application_process_fact(sentence)
                for sentence in candidates[:3]
            )
        if category == "documents":
            document_values = self._unique_texts(
                value
                for sentence in candidates
                for value in self._extract_application_document_values(sentence, language)
            )
            if document_values:
                return document_values
            return self._unique_texts(
                self._shorten_fact_sentence(sentence)
                for sentence in candidates[:3]
            )
        return []

    @staticmethod
    def _extract_chf_amounts(sentence: str, language: str) -> list[str]:
        amounts = re.findall(
            r"CHF\s*\d{1,3}(?:[\s,'’`]\d{3})+(?:\.\d{2})?|CHF\s*\d+",
            sentence,
            flags=re.IGNORECASE,
        )
        normalized = []
        for amount in amounts:
            normalized_amount = re.sub(r"\s+", " ", amount.strip())
            normalized_amount = normalized_amount.replace("’", "'").replace("`", "'")
            normalized_amount = re.sub(r"CHF\s+", "CHF ", normalized_amount, flags=re.IGNORECASE)
            number_part = normalized_amount[4:].strip() if normalized_amount.lower().startswith("chf ") else normalized_amount
            number_part = number_part.replace(" ", "'")
            if language == "en":
                number_part = number_part.replace("'", ",")
            elif "," in number_part and "." not in number_part:
                number_part = number_part.replace(",", "'")
            digits_only = re.sub(r"\D", "", number_part)
            if digits_only and int(digits_only) < 10000:
                continue
            normalized.append(f"CHF {number_part}")
        return normalized

    @staticmethod
    def _extract_cost_values(sentence: str, language: str) -> list[str]:
        amounts = ExecutiveAgentChain._extract_chf_amounts(sentence, language)
        if not amounts:
            return []

        sentence_lower = sentence.lower()
        has_deadline_context = any(
            term in sentence_lower
            for term in ["bewerbungsfrist", "frist", "deadline", "application deadline"]
        )
        dates = ExecutiveAgentChain._extract_future_dates(sentence)
        if has_deadline_context and dates and len(dates) >= len(amounts):
            return [f"{date}: {amount}" for date, amount in zip(dates, amounts)]

        return amounts
    
    @staticmethod
    def _extract_future_dates(sentence: str) -> list[str]:
        month_names = (
            "Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
            "January|February|March|April|May|June|July|August|September|October|November|December"
        )
        season_names = "Herbst|Frühjahr|Fruehjahr|Sommer|Winter|Fall|Autumn|Spring"
        patterns = [
            rf"\b\d{{1,2}}[./]\d{{1,2}}[./]\d{{4}}\b",
            rf"\b\d{{1,2}}\.?\s+(?:{month_names})\s+\d{{4}}\b",
            rf"\b(?:{season_names})\s+\d{{4}}\b",
        ]

        dates = []
        for pattern in patterns:
            dates.extend(re.findall(pattern, sentence, flags=re.IGNORECASE))

        return [
            date.strip()
            for date in dates
            if ExecutiveAgentChain._date_has_current_or_future_year(date)
        ]

    @staticmethod
    def _date_has_current_or_future_year(value: str) -> bool:
        year_match = re.search(r"\b(20\d{2})\b", value)
        if not year_match:
            return False
        return int(year_match.group(1)) >= datetime.now().year

    @staticmethod
    def _sentence_has_only_past_years(sentence: str) -> bool:
        years = [int(year) for year in re.findall(r"\b(20\d{2})\b", sentence or "")]
        return bool(years) and max(years) < datetime.now().year

    @staticmethod
    def _extract_duration_values(sentence: str, language: str) -> list[str]:
        durations = re.findall(
            r"\b\d{1,2}\s*(?:Monate|months)\b",
            sentence,
            flags=re.IGNORECASE,
        )
        return [re.sub(r"\s+", " ", duration.strip()) for duration in durations]

    @staticmethod
    def _format_application_process_fact(sentence: str) -> str:
        sentence = re.sub(r"\s+", " ", sentence).strip(" .")
        if re.search(r"\b1\.\s+", sentence) and re.search(r"\b2\.\s+", sentence):
            parts = re.split(r"\s+\d+\.\s+", re.sub(r"^\s*1\.\s+", "", sentence))
            cleaned_parts = [
                re.sub(r"\s+", " ", part).strip(" .")
                for part in parts
                if part.strip()
            ]
            if cleaned_parts:
                return "; ".join(cleaned_parts[:5])
        return ExecutiveAgentChain._shorten_fact_sentence(sentence)

    @staticmethod
    def _extract_application_document_values(sentence: str, language: str) -> list[str]:
        sentence_lower = sentence.lower()
        values = []
        if "lebenslauf" in sentence_lower or re.search(r"\bcv\b", sentence_lower):
            values.append("Lebenslauf/CV zur Profilprüfung" if language == "de" else "CV for profile review")
        if "online-bewerbung" in sentence_lower or "online application" in sentence_lower:
            values.append("vollständig ausgefüllte Online-Bewerbung" if language == "de" else "completed online application")
        if "zeugnis" in sentence_lower or "certificate" in sentence_lower or "transcript" in sentence_lower:
            values.append("Zeugnisse/Studienabschluss" if language == "de" else "certificates/transcripts")
        if "motivation" in sentence_lower:
            values.append("Motivation" if language == "de" else "motivation")
        if "essay" in sentence_lower:
            values.append("Essay, falls Sie Zuschüsse beantragen" if language == "de" else "essay if applying for tuition support")
        return values

    @staticmethod
    def _score_application_fact_candidate(sentence: str) -> int:
        sentence_lower = sentence.lower()
        score = 0
        if re.search(r"\b1\.\s+", sentence) and re.search(r"\b2\.\s+", sentence):
            score += 8
        for term in [
            "lebenslauf",
            "cv",
            "online-bewerbung",
            "online application",
            "online-assessment",
            "online-interview",
            "zulassungsausschuss",
            "bewerbungsprozess",
            "application process",
        ]:
            if term in sentence_lower:
                score += 2
        if "jetzt bewerben" in sentence_lower:
            score -= 1
        return score

    @staticmethod
    def _shorten_fact_sentence(sentence: str) -> str:
        sentence = re.sub(r"\s+", " ", sentence).strip(" .")
        if len(sentence) <= 180:
            return sentence
        return sentence[:177].rstrip() + "..."

    @staticmethod
    def _unique_texts(values) -> list[str]:
        unique = []
        seen = set()
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(text)
        return unique

    @staticmethod
    def _fact_category_label(category: str, language: str) -> str:
        labels = {
            "de": {
                "cost": "Kosten",
                "start": "Start",
                "deadline": "Bewerbungsfrist",
                "duration": "Dauer",
                "admission": "Zulassung",
                "application_process": "Bewerbungsprozess",
                "documents": "Unterlagen",
            },
            "en": {
                "cost": "Cost",
                "start": "Start",
                "deadline": "Application deadline",
                "duration": "Duration",
                "admission": "Admissions",
                "application_process": "Application process",
                "documents": "Documents",
            },
        }
        return labels.get(language, labels["en"]).get(category, category)

    @staticmethod
    def _format_requested_fact_values(values: list[str] | None, category: str, language: str) -> str:
        selected_values = ExecutiveAgentChain._selected_requested_fact_values(values, category)
        if selected_values:
            selected_values = [
                ExecutiveAgentChain._escape_markdown_ordered_list_marker(value)
                for value in selected_values
            ]
            if category == "cost":
                return "\n  - " + "\n  - ".join(selected_values)
            return "; ".join(selected_values)
        return ExecutiveAgentChain._empty_requested_fact_value(category, language)

    @staticmethod
    def _selected_requested_fact_values(values: list[str] | None, category: str) -> list[str]:
        if not values:
            return []

        if category == "cost":
            selected_values = [values[-1]]
        else:
            limits = {
                "start": 1,
                "deadline": 2,
                "duration": 1,
                "admission": 3,
                "application_process": 1,
                "documents": 3,
            }
            selected_values = values[:limits.get(category, 3)]

        return [
            " ".join(str(value).split())
            for value in selected_values
            if str(value).strip()
        ]

    @staticmethod
    def _escape_markdown_ordered_list_marker(value: str) -> str:
        return re.sub(r"^(\s*\d{1,9})\.(?=\s)", r"\1\\.", value)

    @staticmethod
    def _empty_requested_fact_value(category: str, language: str) -> str:
        if language == "en":
            empty = {
                "cost": "no reliable current tuition amount found",
                "start": "no reliable current start date found",
                "deadline": "no reliable current application deadline found",
                "duration": "no reliable programme duration found",
                "admission": "no reliable admissions detail found",
                "application_process": "no reliable current application process detail found",
                "documents": "no reliable current application document detail found",
            }
            return empty.get(category, "no reliable current detail found")

        empty = {
            "cost": "keine verlässliche aktuelle Kostenangabe gefunden",
            "start": "kein verlässliches aktuelles Startdatum gefunden",
            "deadline": "keine verlässliche aktuelle Bewerbungsfrist gefunden",
            "duration": "keine verlässliche Programmdauer gefunden",
            "admission": "keine verlässlichen Zulassungsdetails gefunden",
            "application_process": "keine verlässlichen aktuellen Angaben zum Bewerbungsprozess gefunden",
            "documents": "keine verlässlichen aktuellen Angaben zu Bewerbungsunterlagen gefunden",
        }
        return empty.get(category, "keine verlässliche aktuelle Angabe gefunden")

    def _format_requested_fact_block(
        self,
        programme_name: str,
        category: str,
        values: list[str] | None,
        language: str,
    ) -> str:
        topic = self._fact_category_label(category, language)
        selected_values = self._selected_requested_fact_values(values, category)
        if not selected_values:
            selected_values = [self._empty_requested_fact_value(category, language)]
        selected_values = [
            self._escape_markdown_ordered_list_marker(value)
            for value in selected_values
        ]
        bullets = "\n".join(f"- {value}" for value in selected_values)
        return f"**{programme_name} {topic}**:\n{bullets}"
    
    def _serve_programme_fact_request(
        self,
        processed_query: str,
        response_language: str,
        programmes: list[str],
    ) -> LeadAgentQueryResponse:
        chain_logger.info(f"Serving programme fact request via retrieve_context tool: {programmes}")
        responses = [
            self._build_programme_fact_response(programme, response_language, processed_query)
            for programme in programmes
        ]
        response = "\n\n".join(responses)
        response = ResponseFormatter.clean_response(ResponseFormatter.remove_tables(response))
        response = ResponseFormatter.format_name_of_university(response, language=response_language)

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

    def _get_programme_facts(self, programme: str, language: str) -> ProgrammeFacts:
        provider = getattr(self, "_programme_facts_provider", None)
        if provider is None:
            return ProgrammeFacts(programme=programme)
        return provider.get_facts(programme, language)

    def _get_programmes_facts(self, programmes: list[str], language: str) -> dict[str, ProgrammeFacts]:
        provider = getattr(self, "_programme_facts_provider", None)
        if provider is None:
            return {
                programme: ProgrammeFacts(programme=programme)
                for programme in programmes
            }

        get_facts_many = getattr(provider, "get_facts_many", None)
        if callable(get_facts_many):
            return get_facts_many(programmes, language)

        return {
            programme: provider.get_facts(programme, language)
            for programme in programmes
        }

    @staticmethod
    def _format_fact_points(points: list[str], fallback: str) -> str:
        if not points:
            return fallback
        return "; ".join(points)

    def _build_programme_fact_summary(self, programme: str, language: str) -> str:
        facts = self._get_programme_facts(programme, language)
        return self._build_programme_fact_summary_from_facts(programme, language, facts)

    def _build_programme_fact_summary_from_facts(
        self,
        programme: str,
        language: str,
        facts: ProgrammeFacts,
    ) -> str:
        programme_name, _ = self._programme_label_and_advisor(programme)
        if language == "en":
            focus = self._format_fact_points(
                facts.focus_points,
                "focus details are not clearly available in the current programme material",
            )
            fit = self._format_fact_points(
                facts.fit_points,
                "admissions requirements should be checked with the current admissions material",
            )
            timing = self._format_fact_points(
                facts.timing_points,
                "current duration, start, deadline, and tuition details are not clearly available in the current programme material",
            )
            return (
                f"**{programme_name}**: {focus}. "
                f"Format, timing, and tuition: {timing}. "
                f"Admissions fit: {fit}."
            )

        focus = self._format_fact_points(
            facts.focus_points,
            "Fokusdetails sind in den aktuellen Programmunterlagen gerade nicht eindeutig verfügbar",
        )
        fit = self._format_fact_points(
            facts.fit_points,
            "Zulassungsanforderungen sollten anhand des aktuellen Zulassungsmaterials geprüft werden",
        )
        timing = self._format_fact_points(
            facts.timing_points,
            "aktuelle Angaben zu Dauer, Start, Fristen und Gebühren sind in den Programmunterlagen gerade nicht eindeutig verfügbar",
        )
        return (
            f"**{programme_name}**: {focus}. "
            f"Format, Timing und Gebühren: {timing}. "
            f"Formaler Fit: {fit}."
        )

    @staticmethod
    def _programme_label_and_advisor(programme: str) -> tuple[str, str]:
        labels = {
            "emba": ("EMBA HSG", "Cyra von Müller"),
            "iemba": ("IEMBA HSG", "Kristin Fuchs"),
            "emba_x": ("emba X", "Teyuna Giger"),
        }
        return labels.get(programme, ("Executive MBA", "dem Admissions Team"))

    def _build_programme_next_steps_response(self, language: str, programme: str) -> str:
        programme_name, advisor = self._programme_label_and_advisor(programme)
        facts = self._get_programme_facts(programme, language)

        if language == "en":
            focus = self._format_fact_points(
                facts.focus_points,
                "the development goal should be clarified with admissions because the current programme material does not contain a clear focus summary",
            )
            fit = self._format_fact_points(
                facts.fit_points,
                "formal requirements should be confirmed from the current admissions material",
            )
            timing = self._format_fact_points(
                facts.timing_points,
                "current start, tuition, and deadline information is not clearly available in the programme material",
            )
            documents = self._format_fact_points(
                facts.document_points,
                "the required application documents should be confirmed in the admissions conversation",
            )
            return (
                f"If **{programme_name}** is currently the strongest option, the next step is a fit and admissions check.\n\n"
                f"1. **Clarify the development goal**: {focus}.\n"
                f"2. **Check formal fit**: {fit}.\n"
                f"3. **Plan timing and tuition**: {timing}.\n"
                f"4. **Prepare the admissions conversation**: {documents}.\n\n"
                f"The right advisor is **{advisor}** for **{programme_name}** if you want a personal consultation."
            )

        focus = self._format_fact_points(
            facts.focus_points,
            "das Entwicklungsziel sollte im Beratungsgespräch anhand der aktuellen Programmunterlagen geklärt werden",
        )
        fit = self._format_fact_points(
            facts.fit_points,
            "die formalen Anforderungen sollten anhand des aktuellen Zulassungsmaterials bestätigt werden",
        )
        timing = self._format_fact_points(
            facts.timing_points,
            "aktuelle Start-, Gebühren- und Fristdaten sind in den Programmunterlagen gerade nicht eindeutig verfügbar",
        )
        documents = self._format_fact_points(
            facts.document_points,
            "die erforderlichen Bewerbungsunterlagen sollten im Zulassungsgespräch bestätigt werden",
        )
        return (
            f"Wenn **{programme_name}** aktuell am besten passt, ist der nächste Schritt eine Fit- und Zulassungsabklärung.\n\n"
            f"1. **Ziel schärfen**: {focus}.\n"
            f"2. **Formalen Fit prüfen**: {fit}.\n"
            f"3. **Timing und Gebühren planen**: {timing}.\n"
            f"4. **Admissions-Gespräch vorbereiten**: {documents}.\n\n"
            f"Die passende Studienberatung ist **{advisor}** für **{programme_name}**, falls Sie eine persönliche Beratung wünschen."
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
        self._conversation_state['suggested_program'] = programme
        booking_active = self._conversation_state.get('handover_requested') is True

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=booking_active,
            show_booking_widget=booking_active,
            relevant_programs=[programme],
        )

    def _get_application_timing_fact_values(
        self,
        programme: str,
        language: str,
    ) -> dict[str, list[str]]:
        categories = ["cost", "start", "deadline"]
        contexts: list[str] = []

        cross_context = self._get_cross_programme_fact_context(language, categories)
        if cross_context:
            contexts.append(cross_context)

        facts_by_category = self._extract_requested_programme_facts(
            context="\n".join(contexts),
            programme=programme,
            categories=categories,
            language=language,
        )

        if self._has_missing_requested_facts(facts_by_category, categories):
            targeted_context = self._get_targeted_programme_fact_context(
                programme=programme,
                language=language,
                user_query=(
                    "Bewerbungsfrist Studiengebühr Programm-Start"
                    if language == "de"
                    else "application deadline tuition programme start"
                ),
                categories=categories,
            )
            if targeted_context:
                contexts.append(targeted_context)
                facts_by_category = self._extract_requested_programme_facts(
                    context="\n".join(contexts),
                    programme=programme,
                    categories=categories,
                    language=language,
                )

        return facts_by_category

    def _format_application_timing_summary(self, programme: str, language: str) -> str:
        facts_by_category = self._get_application_timing_fact_values(programme, language)
        lines: list[str] = []

        start_values = facts_by_category.get("start") or []
        if start_values:
            label = "Start" if language == "de" else "Start"
            lines.append(
                f"- **{label}**: {self._format_requested_fact_values(start_values, 'start', language)}"
            )

        cost_values = facts_by_category.get("cost") or []
        if cost_values:
            label = "Gebühren" if language == "de" else "Tuition"
            lines.append(
                f"- **{label}**: {self._format_requested_fact_values(cost_values, 'cost', language)}"
            )

        deadline_values = facts_by_category.get("deadline") or []
        if deadline_values:
            label = "Bewerbungsfristen" if language == "de" else "Application deadlines"
            lines.append(
                f"- **{label}**: {self._format_requested_fact_values(deadline_values, 'deadline', language)}"
            )

        if not lines:
            return ""

        heading = "Aktuell relevant:" if language == "de" else "Currently relevant:"
        return f"{heading}\n" + "\n".join(lines)

    def _build_application_next_steps_response(self, language: str, programmes: list[str]) -> str:
        programme_labels = {
            "emba": ("EMBA HSG", "Cyra von Müller"),
            "iemba": ("IEMBA HSG", "Kristin Fuchs"),
            "emba_x": ("emba X", "Teyuna Giger"),
        }
        selected = [(p, *programme_labels[p]) for p in programmes if p in programme_labels]

        if len(selected) == 1:
            programme, programme_name, advisor = selected[0]
            facts = self._get_programme_facts(programme, language)
            timing_summary = self._format_application_timing_summary(programme, language)
            timing_block = f"\n\n{timing_summary}" if timing_summary else ""
            if language == "en":
                documents = self._format_fact_points(
                    facts.document_points,
                    "CV, degree certificates/transcripts, leadership scope, motivation, language readiness, and target start timing",
                ).rstrip(". ")
                return (
                    f"For the **{programme_name}** application, the next useful step is to prepare for an admissions "
                    f"conversation with **{advisor}**. Preparation: {documents}. In that conversation, admissions can "
                    f"confirm formal eligibility, documents, deadlines, and the best timing for submission.{timing_block}"
                )
            documents = self._format_fact_points(
                facts.document_points,
                "CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Motivation, Sprachniveau und gewünschter Startzeitpunkt",
            ).rstrip(". ")
            return (
                f"Für die Bewerbung zum **{programme_name}** ist der nächste sinnvolle Schritt die Vorbereitung auf eine "
                f"Zulassungs- und Beratungsabklärung mit **{advisor}**. Als Vorbereitung relevant: {documents}. Dabei "
                f"können formaler Fit, Unterlagen, Fristen und der beste Zeitpunkt für die Einreichung geklärt werden.{timing_block}"
            )

        if language == "en":
            return (
                "For the application step, the important point is to clarify the right programme before submitting "
                "documents. Prepare your CV, degree certificates, leadership scope, motivation, language readiness, and "
                "preferred start timing. Because more than one Executive MBA option is still relevant, first narrow the "
                "target programme before submitting documents."
            )

        return (
            "Für den Bewerbungsschritt sollte zuerst geklärt werden, welches der drei Executive-MBA-Programme wirklich "
            "das richtige Ziel ist. Vorbereiten sollten Sie CV, Studienabschluss, Führungsverantwortung, Motivation, "
            "Sprachniveau und den gewünschten Startzeitpunkt. Da noch mehrere Programme relevant sind, sollte vor der "
            "Einreichung zuerst das Zielprogramm eingegrenzt werden."
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
        if len(programmes) == 1:
            self._conversation_state["suggested_program"] = programmes[0]

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

    def _build_application_process_details_response(self, language: str, programmes: list[str]) -> str:
        normalized_programmes = [p for p in programmes if p in {"emba", "iemba", "emba_x"}]
        if not normalized_programmes:
            normalized_programmes = ["emba", "iemba", "emba_x"]

        if len(normalized_programmes) == 1:
            programme = normalized_programmes[0]
            programme_name, _ = self._programme_label_and_advisor(programme)
            facts = self._get_programme_facts(programme, language)

            if language == "en":
                fit = self._format_fact_points(
                    facts.fit_points,
                    "formal requirements should be checked against the current admissions material",
                )
                documents = self._format_fact_points(
                    facts.document_points,
                    "CV, certificates, leadership scope, motivation, goals, and language readiness should be prepared and confirmed with admissions",
                )
                timing = self._format_fact_points(
                    facts.timing_points,
                    "current deadlines, start dates, tuition, and available seats are not clearly available in the programme material",
                )
                focus = self._format_fact_points(
                    facts.focus_points,
                    "the programme goal should be clarified against the current programme material",
                )
                return (
                    f"For the **{programme_name}** application process, the practical sequence is:\n\n"
                    f"1. **Fit check**: {fit}.\n"
                    f"2. **Prepare documents**: {documents}.\n"
                    f"3. **Plan timing and tuition**: {timing}.\n"
                    f"4. **Admissions conversation**: confirm formal eligibility, programme fit, goals, timing, current "
                    f"deadlines, and open questions. Programme goal: {focus}.\n"
                    "5. **Submit application and enrol**: admissions confirms the submission route, missing documents, "
                    "decision process, enrolment steps, and payment details."
                )

            fit = self._format_fact_points(
                facts.fit_points,
                "formale Anforderungen sollten anhand des aktuellen Zulassungsmaterials geprüft werden",
            )
            documents = self._format_fact_points(
                facts.document_points,
                "CV, Zeugnisse, Führungsverantwortung, Motivation, Ziele und Sprachniveau sollten vorbereitet und mit Admissions bestätigt werden",
            )
            timing = self._format_fact_points(
                facts.timing_points,
                "aktuelle Fristen, Startdaten, Gebühren und verfügbare Plätze sind in den Programmunterlagen gerade nicht eindeutig verfügbar",
            )
            focus = self._format_fact_points(
                facts.focus_points,
                "das Programmziel sollte anhand der aktuellen Programmunterlagen geklärt werden",
            )
            return (
                f"Für die Bewerbung zum **{programme_name}** läuft der Prozess praktisch so:\n\n"
                f"1. **Fit prüfen**: {fit}.\n"
                f"2. **Unterlagen vorbereiten**: {documents}.\n"
                f"3. **Timing und Gebühren planen**: {timing}.\n"
                f"4. **Zulassungs-/Beratungsgespräch**: formaler Fit, Programm-Fit, Ziele, Timing, aktuelle Fristen und "
                f"offene Fragen klären. Programmziel: {focus}.\n"
                "5. **Bewerbung einreichen und Einschreibung finalisieren**: Admissions bestätigt Einreichungsweg, "
                "fehlende Unterlagen, Entscheidungsprozess, Einschreibung und Zahlungs-/Gebührenthemen."
            )

        facts_by_programme = self._get_programmes_facts(normalized_programmes, language)
        summaries = [
            self._build_programme_fact_summary_from_facts(
                programme,
                language,
                facts_by_programme.get(programme, ProgrammeFacts(programme=programme)),
            )
            for programme in normalized_programmes
        ]
        joined_summaries = "\n".join(f"- {summary}" for summary in summaries)

        if language == "en":
            return (
                "Before applying, first decide which programme you want to target. The process then follows the same "
                "structure: fit check, documents, admissions conversation, "
                "application submission, decision, and enrolment.\n\n"
                f"{joined_summaries}\n\n"
                "For the conversation, prepare CV, degree certificates/transcripts, leadership overview, motivation, "
                "language readiness, and preferred timing. Exact current facts should be confirmed by admissions."
            )
        return (
            "Vor der Bewerbung sollte zuerst geklärt werden, welches Programm Sie konkret ansteuern. Danach ist der "
            "Ablauf grundsätzlich: Fit prüfen, Unterlagen vorbereiten, "
            "Zulassungs-/Beratungsgespräch, Bewerbung einreichen, Entscheid und Einschreibung.\n\n"
            f"{joined_summaries}\n\n"
            "Für das Gespräch sollten Sie CV, Studienabschluss/Zeugnisse, Führungsverantwortung, Motivation, Sprachniveau "
            "und gewünschten Startzeitpunkt vorbereiten. Konkrete aktuelle Angaben sollten durch Admissions bestätigt werden."
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

    def _profile_has_emba_hsg_signal(self, query: str, language: str) -> bool:
        context_lower = self._human_context_for_recommendation(query)
        experience_years = self._extract_experience_years(query)
        leadership_years = self._extract_leadership_years(query)
        if not experience_years or experience_years < 5:
            return False
        if not leadership_years or leadership_years < 3:
            return False

        disqualifying_goal_terms = [
            "international",
            "global",
            "englisch",
            "english",
            "ausland",
            "cross-border",
            "technology",
            "technologie",
            "digital",
            "digitalisierung",
            "innovation",
            "transformation",
            "nachhaltigkeit",
            "sustainability",
            "eth",
        ]
        if any(term in context_lower for term in disqualifying_goal_terms):
            return False

        german_preference_terms = [
            "deutsch",
            "german",
            "dach",
            "berufsbegleitend",
            "deutschsprachig",
        ]
        return language == "de" or any(term in context_lower for term in german_preference_terms)

    def _human_context_for_recommendation(self, query: str) -> str:
        texts = [query]
        for message in getattr(self, "_conversation_history", []) or []:
            if not isinstance(message, HumanMessage):
                continue
            content = getattr(message, "content", "") or getattr(message, "text", "")
            if isinstance(content, list):
                texts.append(" ".join(str(part) for part in content))
            else:
                texts.append(str(content))
        return "\n".join(texts).lower()

    def _recommended_programme_from_profile(self, query: str, language: str, profile_context: bool) -> str | None:
        context_lower = self._human_context_for_recommendation(query)
        tech_transformation_terms = [
            "nachhaltigkeit",
            "nachhaltige",
            "sustainability",
            "digitalisierung",
            "digitalization",
            "digitalisation",
            "technology",
            "technologie",
            "innovation",
            "transformation",
        ]
        if not profile_context and any(term in context_lower for term in tech_transformation_terms):
            return "emba_x"

        international_terms = [
            "international focus",
            "internationaler fokus",
            "international ausgerichtet",
            "global",
            "asia-pacific",
            "apac",
            "cross-border",
        ]
        if not profile_context and any(term in context_lower for term in international_terms):
            return "iemba"

        if profile_context and self._profile_has_emba_hsg_signal(query, language):
            return "emba"

        return None

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
        recommended_programme: str | None = None,
    ) -> str:
        if language == 'en':
            if not detailed:
                if not profile_context and not recommended_programme:
                    return (
                        "At HSG, there are three relevant Executive MBA options. The main difference is not that one is "
                        "universally better, but their language, focus, network, and development goal.\n\n"
                        "1. **EMBA HSG**: German-speaking programme for DACH-focused general management, leadership, "
                        "strategy, finance, organisation, and governance.\n"
                        "2. **IEMBA HSG**: English-speaking international option for leaders who want global exposure, "
                        "international peer learning, and management perspective across markets.\n"
                        "3. **emba X**: English-speaking joint-degree option with **ETH Zurich** and **University of St.Gallen** "
                        "for leadership at the intersection of business, technology, innovation, and transformation.\n\n"
                        "Would you like details on costs, start dates, deadlines, duration, or admissions requirements, "
                        "or should I recommend the most suitable programme based on the information you share?"
                    )

                if recommended_programme == "emba":
                    return (
                        "Based on your German-language preference and leadership experience, **EMBA HSG** is the "
                        "strongest fit. Your professional and leadership experience is in the usual Executive MBA range; "
                        "formal eligibility still needs to be confirmed against the current admissions requirements.\n\n"
                        "**IEMBA HSG** remains relevant mainly if your next goal is international exposure. **emba X** "
                        "remains relevant mainly if your goal is technology, innovation, or transformation."
                    )

                if recommended_programme == "iemba":
                    return (
                        "Based on your international focus, **IEMBA HSG** is the strongest fit. It is the Executive MBA "
                        "option built around international management perspective, global peer learning, and cross-border "
                        "leadership.\n\n"
                        "**EMBA HSG** remains relevant mainly for German-speaking DACH general management. **emba X** "
                        "remains relevant mainly if technology, innovation, or transformation is the central goal."
                    )

                if recommended_programme == "emba_x":
                    return (
                        "Based on your technology, innovation, transformation, or sustainability focus, **emba X** is the "
                        "strongest fit. It is the Executive MBA option designed for leadership at the intersection of "
                        "business and technology with the ETH Zurich and University of St.Gallen joint-degree setting.\n\n"
                        "**IEMBA HSG** remains relevant mainly if international exposure is the primary goal. **EMBA HSG** "
                        "remains relevant mainly for German-speaking DACH general management."
                    )

                return (
                    "The information you shared helps clarify the admissions level; the Executive MBA options should be "
                    "checked against the current requirements. The programme choice should now be based on your "
                    "development goals, not on an automatic classification.\n\n"
                    "1. **EMBA HSG**: strongest if your goal is DACH-focused general management, organisational leadership, "
                    "strategy, finance, and governance.\n"
                    "2. **IEMBA HSG**: strongest if your goal is international exposure, global peer learning, or cross-border work.\n"
                    "3. **emba X**: strongest if your goal is digital transformation, technology, innovation, or large-scale change.\n\n"
                    "Would you like details on costs, start dates, deadlines, duration, or admissions requirements, "
                    "or should I recommend the most suitable programme based on the information you share?"
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
                    "For a professional or leader comparing options, the practical value is strategy, finance, governance, "
                    "organisation design, negotiation, and change leadership in German-speaking organisations. The capstone "
                    "project can be tied to a real organisational or transformation topic.\n\n"
                    "**IEMBA HSG** aims to build international management perspective. The value is not only the English "
                    "language; it is the global cohort and modules across different regions. That is useful when your work "
                    "involves international partners, cross-border teams, global markets, or comparison across business "
                    "environments.\n\n"
                    "**emba X** aims at leadership where business and technology meet. It is the most relevant option if "
                    "your goals include digital transformation, technology-led business models, AI/data initiatives, "
                    "innovation, or large organisational change. Its distinctive feature is the integrated **ETH Zurich** "
                    "plus **University of St.Gallen** joint-degree setting and access to both alumni networks."
                )

            if not profile_context and not recommended_programme:
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
                "- Choose **EMBA HSG** if your main goal is stronger economic and organisational steering in the DACH "
                "environment: strategy, budgeting, governance, leadership, negotiation, and operational change.\n"
                "- Choose **IEMBA HSG** if your main goal is international exposure: learning with a global cohort, "
                "working across markets or organisations, and building confidence for international partnerships.\n"
                "- Choose **emba X** if your main goal is transformation through technology: digitalisation, innovation "
                "portfolios, data/AI initiatives, new business models, or culture change around new tools.\n\n"
                "Based on the information shared so far, all three can remain worth comparing. The deciding factor is "
                "whether your next development goal is DACH management depth, international management breadth, or "
                "technology-led transformation."
            )

        if not detailed:
            if not profile_context and not recommended_programme:
                return (
                    "Bei HSG gibt es drei relevante Executive-MBA-Optionen. Der Unterschied liegt nicht darin, dass ein "
                    "Programm pauschal besser ist, sondern in Sprache, Fokus, Netzwerk und Entwicklungsziel.\n\n"
                    "1. **EMBA HSG**: deutschsprachig, DACH-Fokus, General Management, Leadership, Strategie, Finanzen, "
                    "Organisation und Governance.\n"
                    "2. **IEMBA HSG**: englischsprachig und international ausgerichtet, mit Fokus auf globale Perspektive, "
                    "internationale Peer Group und Führung über Märkte hinweg.\n"
                    "3. **emba X**: englischsprachiges Joint Degree mit **ETH Zürich** und **Universität St.Gallen**, mit "
                    "Fokus auf Business, Technologie, Innovation und Transformation.\n\n"
                    "Interessieren Sie sich für Kosten, Startdatum, Fristen, Dauer oder Zulassungsdetails, oder möchten "
                    "Sie, dass ich ein passendes Programm anhand Ihrer Angaben empfehle?"
                )

            if recommended_programme == "emba":
                return (
                    "Auf Basis Ihrer deutschsprachigen Präferenz und Ihrer Führungserfahrung ist **EMBA HSG** der "
                    "stärkste Fit. Ihre Berufs- und Führungserfahrung liegt im typischen Executive-MBA-Profil; die "
                    "formale Zulassung muss dennoch anhand der aktuellen Anforderungen geprüft werden.\n\n"
                    "**IEMBA HSG** bleibt vor allem relevant, wenn Internationalität Ihr nächstes Ziel ist. **emba X** "
                    "bleibt vor allem relevant, wenn Technologie, Innovation oder Transformation im Zentrum stehen."
                )

            if recommended_programme == "iemba":
                return (
                    "Auf Basis Ihres internationalen Fokus ist **IEMBA HSG** der stärkste Fit. Das Programm ist auf "
                    "internationale Managementperspektive, globale Peer Learning und Führung über Märkte hinweg "
                    "ausgerichtet.\n\n"
                    "**EMBA HSG** bleibt vor allem relevant für deutschsprachiges General Management im DACH-Kontext. "
                    "**emba X** bleibt vor allem relevant, wenn Technologie, Innovation oder Transformation im Zentrum stehen."
                )

            if recommended_programme == "emba_x":
                return (
                    "Auf Basis Ihres Fokus auf Technologie, Innovation, Transformation oder Nachhaltigkeit ist **emba X** "
                    "der stärkste Fit. Das Programm ist auf Führung an der Schnittstelle von Business und Technologie "
                    "ausgerichtet und verbindet **ETH Zürich** mit der **Universität St.Gallen**.\n\n"
                    "**IEMBA HSG** bleibt vor allem relevant, wenn Internationalität das Hauptziel ist. **EMBA HSG** "
                    "bleibt vor allem relevant für deutschsprachiges General Management im DACH-Kontext."
                )

            return (
                "Ihre Angaben helfen vor allem, die Zulassungsebene einzuordnen; die Executive-MBA-Optionen sollten anhand "
                "der aktuellen Anforderungen geprüft werden. Die Programmwahl sollte jetzt über Ihre Entwicklungsziele "
                "laufen, nicht über eine automatische Einordnung.\n\n"
                "1. **EMBA HSG**: naheliegend, wenn Sie DACH-orientiertes General Management, Strategie, Finanzen, Organisation und Governance vertiefen wollen.\n"
                "2. **IEMBA HSG**: naheliegend, wenn Sie internationaler arbeiten, vergleichen oder kooperieren möchten.\n"
                "3. **emba X**: naheliegend, wenn Digitalisierung, Technologie, Innovation oder grosse Transformation zentral sind.\n\n"
                "Interessieren Sie sich für Kosten, Startdatum, Fristen, Dauer oder Zulassungsdetails, oder möchten "
                "Sie, dass ich ein passendes Programm anhand Ihrer Angaben empfehle?"
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
                "**EMBA HSG** zielt auf breite General-Management-Kompetenz im DACH-Raum. Das ist relevant, wenn Sie "
                "Strategie, Finanzen, Governance, Organisation, Verhandlung und Change Management stärken wollen. Das "
                "Capstone-Projekt kann direkt auf ein reales Organisations- oder Transformationsvorhaben ausgerichtet "
                "werden.\n\n"
                "**IEMBA HSG** zielt auf internationale Managementkompetenz. Der Mehrwert liegt in der englischsprachigen "
                "globalen Kohorte und den internationalen Modulen. Das ist besonders sinnvoll, wenn Sie mit internationalen "
                "Partnern, Märkten, Teams oder Organisationen arbeiten oder Führungsfragen über Ländergrenzen hinweg "
                "vergleichen möchten.\n\n"
                "**emba X** zielt auf Führung an der Schnittstelle von Business und Technologie. Das ist besonders relevant, "
                "wenn Ihre Ziele Digitalisierung, technologiegetriebene Geschäftsmodelle, datenbasierte Prozesse, "
                "Innovation oder grosse Transformationsprojekte betreffen. Der besondere Punkt ist die Kombination aus "
                "**ETH Zürich** und **Universität St.Gallen** sowie der Zugang zu beiden Netzwerken."
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
            "DACH-Umfeld vertiefen wollen: Budget, Governance, Personalführung, Verhandlung und Change.\n"
            "- **IEMBA HSG** passt am besten, wenn Sie internationaler arbeiten möchten: Vergleich von Märkten und "
            "Organisationen, globale Peer Group, internationale Kooperationen oder länderübergreifende Verantwortung.\n"
            "- **emba X** passt am besten, wenn Technologie und Transformation im Zentrum stehen: Digitalisierung, "
            "datenbasierte Prozesse, neue Geschäftsmodelle, Innovationsportfolios oder kultureller Wandel.\n\n"
            "Anhand der bisherigen Angaben können alle drei Programme weiterhin vergleichbar bleiben. Ausschlaggebend "
            "ist, ob Ihr nächster Entwicklungsschwerpunkt DACH-Management, Internationalität oder technologiegetriebene "
            "Transformation ist."
        )

    def _serve_programme_overview(
        self,
        processed_query: str,
        response_language: str,
        detailed: bool,
        profile_context: bool = False,
    ) -> LeadAgentQueryResponse:
        chain_logger.info("Serving deterministic three-programme overview without a model call.")
        recommended_programme = (
            self._recommended_programme_from_profile(
                processed_query,
                response_language,
                profile_context,
            )
            if not detailed
            else None
        )
        response = self._build_programme_overview_response(
            response_language,
            detailed=detailed,
            profile_context=profile_context,
            recommended_programme=recommended_programme,
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
        if recommended_programme and hasattr(self, "_conversation_state"):
            self._conversation_state["suggested_program"] = recommended_programme

        return LeadAgentQueryResponse(
            response=response,
            language=response_language,
            confidence_fallback=False,
            should_cache=False,
            processed_query=processed_query,
            appointment_requested=False,
            show_booking_widget=False,
            relevant_programs=[recommended_programme] if recommended_programme else ["emba", "iemba", "emba_x"],
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
            config['configurable']['thread_id'] = thread_id or self._user_id

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
