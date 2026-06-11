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
from src.rag.middleware import AgentChainMiddleware as chainmdw
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf
from src.rag.input_handler import InputHandler
from src.rag.conversation_state import ConversationStateManager
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian
from src.rag.language_detection import LanguageDetector
from src.rag.tool_schemas import RetrieveContextInput

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
        self._cache = Cache.get_cache()

        if config.chain.EVALUATE_RESPONSE_QUALITY:
            from src.rag.quality_score_handler import QualityScoreHandler
            self._quality_handler = QualityScoreHandler()

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

        # Profile tracking lives in its own component (adopted from the
        # chatbot-decoupling branch) to keep this class a thin orchestrator.
        self._state_manager = ConversationStateManager(self)

        chain_logger.info(f"Initialized new Agent Chain for language '{language}' with user_id: {self._user_id}")

    def _state_tracker(self) -> ConversationStateManager:
        """Return a state manager, including for tests that bypass __init__."""
        manager = getattr(self, "_state_manager", None)
        if manager is None:
            manager = ConversationStateManager(self)
            self._state_manager = manager
        return manager

    def _retrieve_context(self, query: str, program: str, language: str = None):
        """
        Send the query to the vector database to retrieve additional information about the program.

        Args:
            query: Keywords depicting information you want to retrieve in the primary language.
            program: Name of the program (either 'emba', 'iemba' or 'emba x') for which the information is requested.
            language: Optional parameter (either 'en' for English language or 'de' for German language). This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language. Use this parameter only if there's not enough information in your main language.
        """
        lang = language if language in ['en', 'de'] else self._initial_language
        # Adopted from chatbot-decoupling: normalise the programme id before
        # filtering. The DB tags chunks with canonical programme ids.
        normalized = self._normalise_programme_id(program)
        db_program = {'emba': 'emba', 'iemba': 'iemba', 'emba_x': 'emba_x'}.get(normalized)
        property_filters = {'programs': [db_program]} if db_program else {'programs': [program]}
        try:
            response, _ = self._dbservice.query(
                query=query,
                lang=lang,
                limit=config.get('TOP_K_RETRIEVAL'),
                property_filters=property_filters,
            )
            # Hallucination fix: include source metadata per chunk so the
            # model can keep programmes apart and ground its answer, instead
            # of receiving an anonymous wall of concatenated text.
            serialized_chunks = []
            for doc in response.objects:
                props = doc.properties or {}
                body = props.get('body', '')
                if not body:
                    continue
                programs = props.get('programs') or []
                source = props.get('source') or 'unknown'
                header = f"[programme: {', '.join(programs) if programs else 'unspecified'} | source: {source}]"
                serialized_chunks.append(f"{header}\n{body}")
            serialized = '\n\n'.join(serialized_chunks)
            # Hallucination guard: an empty tool result silently invited the
            # model to answer from world knowledge. Make the gap explicit and
            # instruct the model to acknowledge it instead of inventing facts.
            if not serialized.strip():
                chain_logger.warning(
                    f"retrieve_context returned no documents (program='{program}', lang='{lang}', query='{query}')"
                )
                return (
                    "NO_CONTEXT_FOUND: The knowledge base returned no documents for this "
                    "query. Do NOT answer from memory or general knowledge. Tell the user "
                    "that this specific information is not available right now and "
                    "recommend confirming it with the admissions team."
                )
            return serialized
        except Exception as e:
            raise e

    def _init_agents(self):
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
                "Arguments: query, program, optional language. "
                "Language guidance: use 'de' for EMBA HSG (German-speaking programme), "
                "'en' for IEMBA and emba X (English-speaking programmes); "
                "write the query in that same language."
            ),
            return_direct=False,
            parse_docstring=False,
        )
        self._retrieve_context_tool = tool_retrieve_context

        agents = {
            'lead': create_agent(
                name="lead_agent",
                model=modelconf.get_main_agent_model(),
                tools=[tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(
                    'lead',
                    language=self._initial_language,
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
        return agents, run_config


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
            self._state_tracker().previous_response_offered_booking()
            and any(contains_term(term) for term in acceptance_terms)
        )

    def reset_conversation_state(self) -> None:
        """Clear in-memory conversation state while keeping the same session id."""
        self._conversation_history = []
        self._pending_continuation = None
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

    def _log_user_profile(self) -> None:
        """Backward-compatible wrapper for tests/callers using the old chain API."""
        self._state_tracker().log_user_profile()

    def _update_conversation_state(self, user_query: str, agent_response: str) -> None:
        """Backward-compatible wrapper for tests/callers using the old chain API."""
        self._state_tracker().update(user_query, agent_response)

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
    def query(self, query: str, on_delta=None) -> LeadAgentQueryResponse:
        """
        Phase 1: Validation, Scope-Check and language detection.
        Does not call the agent directly.

        Args:
            on_delta: Optional callback receiving displayable text deltas while
                the lead agent streams its answer. Early-return paths (scope
                check, cache hits, invalid input) skip streaming and only
                return the final response.
        """
        # Latency monitoring: per-step timings are logged so regressions
        # show up immediately instead of being guessed at later.
        self._turn_start_time = perf_counter()

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
        preprocess_elapsed = perf_counter() - self._turn_start_time
        chain_logger.info(f"[timing] preprocessing: {preprocess_elapsed:.2f}s")

        response = self._query_lead(query, on_delta=on_delta)

        total_elapsed = perf_counter() - self._turn_start_time
        chain_logger.info(f"[timing] total turn: {total_elapsed:.2f}s")
        
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


    def _query_lead(self, preprocessed_query: str, on_delta=None) -> LeadAgentQueryResponse:
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
        # Latency fix: cap the history sent to the model. The full history
        # grew unbounded, making every turn slower and more expensive.
        max_history = config.chain.MAX_HISTORY_MESSAGES
        history_window = (
            self._conversation_history[-max_history:]
            if max_history and max_history > 0
            else self._conversation_history
        )
        structured_response = self._query(
            agent=self._agents['lead'],
            messages=history_window + [language_instruction],
            on_delta=on_delta,
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
            self._state_manager.update(preprocessed_query, history_response)
            
            message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])
            if message_count % 5 == 0 or self._conversation_state.get('suggested_program'):
                self._state_manager.log_user_profile()

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

    def _extract_programmes_from_text(self, text: str) -> list[str]:
        """Return normalised programme ids mentioned in the text.

        Most specific names are matched first so "emba X" is not
        misclassified as the generic EMBA HSG. Used by the profile tracking
        to record programme interest.
        """
        text_lower = (text or "").lower()
        if not text_lower:
            return []

        found: list[str] = []
        if "emba x" in text_lower or "embax" in text_lower:
            found.append("emba_x")
        if "iemba" in text_lower or "international emba" in text_lower or "international executive mba" in text_lower:
            found.append("iemba")
        # Generic EMBA only counts when it is not part of an emba X / IEMBA mention
        stripped = (
            text_lower
            .replace("emba x", " ")
            .replace("embax", " ")
            .replace("iemba", " ")
            .replace("international emba", " ")
        )
        if re.search(r"\bemba\b", stripped):
            found.append("emba")
        return found

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

    @staticmethod
    def _chunk_text(chunk) -> str:
        """Best-effort extraction of text content from a streamed message chunk."""
        content = getattr(chunk, 'content', None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(part.get('text', ''))
                elif isinstance(part, str):
                    parts.append(part)
            return ''.join(parts)
        return ""

    def _invoke_streaming(self, agent, messages: list, config, on_delta):
        """
        Stream the agent loop, pushing displayable text deltas to `on_delta`.
        Returns the final graph state (same shape as agent.invoke), or None
        when streaming is unavailable so the caller can fall back to invoke().
        """
        from src.rag.stream_parser import ResponseFieldStreamParser
        parser = ResponseFieldStreamParser(allow_plain_text=False)
        last_values = None
        try:
            for mode, payload in agent.stream(
                {"messages": messages},
                config=config,
                context=AgentContext(agent_name=agent.name),
                stream_mode=["messages", "values"],
            ):
                if mode == "values":
                    last_values = payload
                elif mode == "messages":
                    chunk = payload[0] if isinstance(payload, tuple) else payload
                    text = self._chunk_text(chunk)
                    if text:
                        delta = parser.feed(text)
                        if delta:
                            on_delta(delta)
        except Exception as e:
            chain_logger.warning(
                f"Streaming failed for {agent.name} ({e}); falling back to blocking invoke."
            )
            return None
        return last_values

    def _query(self, agent, messages: list, thread_id: str = None, on_delta=None) -> StructuredAgentResponse:
        try:
            config = self._config.copy()
            config['configurable']['thread_id'] = thread_id or self._user_id

            invoke_start = perf_counter()
            result = None
            if on_delta is not None:
                result = self._invoke_streaming(agent, messages, config, on_delta)
            if result is None:
                result: AIMessage = agent.invoke(
                    {"messages": messages},
                    config=config,
                    context=AgentContext(agent_name=agent.name),
                )
            chain_logger.info(
                f"[timing] agent loop ({agent.name}): {perf_counter() - invoke_start:.2f}s"
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
