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

import uuid, random

from src.database.weavservice import WeaviateService

from src.rag.conversation_analysis import *
from src.rag.utilclasses import *
from src.const.agent_response_constants import *
from src.rag.middleware import AgentChainMiddleware as chainmdw
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf
from src.rag.input_handler import InputHandler
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian
from src.rag.language_detection import LanguageDetector
from src.rag.conversation_state import ConversationStateManager

from src.utils.logging import get_logger
from src.utils.lang import get_language_name
from src.config import config

from ..cache.cache import Cache

chain_logger = get_logger('agent_chain')

class ExecutiveAgentChain:
    def __init__(self, language: str = 'en', session_id: str | None = None) -> None:
        self._initial_language  = language
        self._stored_language = language 

        # Generate unique user ID for this session
        self._user_id = session_id or str(uuid.uuid4())

        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agents()
        self._conversation_history = [] 
        self._cache = Cache.get_cache()
        self._language_detector = LanguageDetector()

        # Initialize conversation state with user profile tracking
        self.state_manager = ConversationStateManager(self._user_id)

        # Track scope violations for escalation
        self._scope_violation_counts: dict[str, int] = {}
        self._aggressive_violation_count = 0

        if config.chain.EVALUATE_RESPONSE_QUALITY:
            from src.rag.quality_score_handler import QualityScoreHandler
            self._quality_handler = QualityScoreHandler()

        chain_logger.info(f"Initialized new Agent Chain for language '{language}' with user_id: {self._user_id}")


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
            return_direct=False,
            parse_docstring=True,
        )

        lead_agent_tools = (sub_provider.get_subagent_tools() 
            if config.chain.ENABLE_SUBAGENTS 
            else [tool_retrieve_context])

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
            self.state_manager.conversation_state['user_language'] = explicit_switch
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
                self.state_manager.conversation_state['user_language'] = detected_language

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
                    "show_booking_widget":   response.show_booking_widget,
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
        explicit_booking_intent = is_explicit_booking_intent(self._conversation_history, preprocessed_query)
        booking_preference_follow_up = (
            self.state_manager.conversation_state.get('handover_requested') is True
            and previous_response_requested_booking_preferences(self._conversation_history)
            and is_booking_preference_follow_up(preprocessed_query)
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

        # 4. Formatting
        if config.chain.ENABLE_RESPONSE_CHUNKING:
            formatted_response = ResponseFormatter.format_response(
                agent_response, agent_type='lead', enable_chunking=True, language=response_language
            )
        else:
            formatted_response = ResponseFormatter.remove_tables(agent_response)

        formatted_response = ResponseFormatter.clean_response(formatted_response)

        confidence_fallback = False
        if config.chain.EVALUATE_RESPONSE_QUALITY:
            quality_evaluation = self._quality_handler.evaluate_response_quality(preprocessed_query, formatted_response)

            chain_logger.info(f"Quality Score: {quality_evaluation.overall_score:1.2f}")

            if quality_evaluation.overall_score < config.chain.CONFIDENCE_THRESHOLD:
                confidence_fallback = True
                formatted_response = CONFIDENCE_FALLBACK_MESSAGE[response_language]
                chain_logger.info("Fallback Mechanism activated!")

        # Add to history
        self._conversation_history.append(AIMessage(formatted_response))

        # 6. Profiling
        if config.convstate.TRACK_USER_PROFILE:
            self.state_manager.update_conversation_state(preprocessed_query, formatted_response)
            
            message_count = len([m for m in self._conversation_history if isinstance(m, HumanMessage)])
            if message_count % 5 == 0 or self.state_manager.conversation_state.get('suggested_program'):
                self.state_manager.log_user_profile()

        formatted_response = ResponseFormatter.format_name_of_university(formatted_response, language=response_language)
        booking_flow_requested = explicit_booking_intent or booking_preference_follow_up
        appointment_requested = bool(booking_flow_requested)
        show_booking_widget = bool(
            booking_flow_requested and (
                structured_response.show_booking_widget
                or response_commits_to_showing_booking_widget(formatted_response)
            )
        )

        if structured_response.appointment_requested and not booking_flow_requested:
            chain_logger.info("Suppressed booking state because no user-led booking intent was detected.")
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
