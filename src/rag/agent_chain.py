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
import random

from src.database.weavservice import WeaviateService

from src.rag.utilclasses import *
from src.const.agent_response_constants import *
from src.rag.middleware import (
    AgentChainMiddleware as chainmdw,
)
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf
from src.rag.programme_facts import JsonProgrammeFactsProvider
from src.rag.response_formatter import ResponseFormatter
from src.rag.language_detection import LanguageDetector
from src.rag.tool_schemas import RetrieveContextInput
from src.rag.chatbot_control_flow import ChatbotControlFlow
from src.rag.conversation_state import ConversationStateManager
from src.rag.deterministic_responses import DeterministicResponsePolicy
from src.rag.deterministic_routes import DeterministicRoutes
from src.rag.programme_fact_responses import ProgrammeFactResponses

from src.utils.logging import get_logger
from src.utils.lang import get_language_name
from src.config import config

from ..cache.cache import Cache

chain_logger = get_logger("agent_chain")


class ExecutiveAgentChain:
    _COMPONENTS = (
        ("_control_flow", ChatbotControlFlow),
        ("_conversation_state_manager", ConversationStateManager),
        ("_deterministic_routes", DeterministicRoutes),
        ("_programme_fact_responses", ProgrammeFactResponses),
    )

    def __init__(self, language: str = "en", session_id: str | None = None) -> None:
        self._initial_language = language
        self._stored_language = language
        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agents()
        self._conversation_history = []
        self._pending_continuation: str | None = None
        self._programme_overview_detail_level = 0
        self._programme_overview_profile_context = False
        self._cache = Cache.get_cache()
        self._deterministic_policy = DeterministicResponsePolicy.from_config()
        self._programme_facts_provider = (
            JsonProgrammeFactsProvider(self._retrieve_context_via_tool)
            if config.chain.USE_PROGRAMME_FACTS
            else None
        )

        if config.chain.EVALUATE_RESPONSE_QUALITY:
            from src.rag.quality_score_handler import QualityScoreHandler

            self._quality_handler = QualityScoreHandler()

        self._language_detector = LanguageDetector()

        # Generate unique user ID for this session
        self._user_id = session_id or str(uuid.uuid4())

        # Initialize conversation state with user profile tracking
        self._conversation_state: ConversationState = {
            "session_id": self._user_id,
            "user_id": self._user_id,
            "user_language": None,
            "user_name": None,
            "experience_years": None,
            "leadership_years": None,
            "field": None,
            "interest": None,
            "qualification_level": None,
            "program_interest": [],
            "suggested_program": None,
            "handover_requested": None,
            "topics_discussed": [],
            "preferences_known": False,
        }

        # Track repeated fallback/redirect uses for escalation.
        self._fallback_counters = {
            "invalid_input": 0,
            "aggressive": 0,
            "scope_violations": {},
        }
        self._conversation_state_manager = ConversationStateManager(self)
        self._deterministic_routes = DeterministicRoutes(self)
        self._programme_fact_responses = ProgrammeFactResponses(self)
        self._control_flow = ChatbotControlFlow(self)

        chain_logger.info(
            f"Initialized new Agent Chain for language '{language}' with user_id: {self._user_id}"
        )

    def _get_component(self, attr_name: str, component_cls):
        component = self.__dict__.get(attr_name)
        if component is None:
            component = component_cls(self)
            self.__dict__[attr_name] = component
        return component

    def __getattr__(self, name):
        for attr_name, component_cls in self._COMPONENTS:
            if getattr(component_cls, name, None) is not None:
                return getattr(self._get_component(attr_name, component_cls), name)
        raise AttributeError(f"{type(self).__name__!s} object has no attribute {name!r}")

    def query(self, query: str) -> LeadAgentQueryResponse:
        return self._get_component("_control_flow", ChatbotControlFlow).query(query)

    @staticmethod
    def _subagent_retrieval_fallback(program: str) -> str:
        fallback_by_program = {
            "emba": (
                "Die Kontextdatenbank ist momentan nicht verfuegbar. Ich kann deshalb keine "
                "aktuellen Fakten zum **EMBA HSG** nachladen und sollte keine Preise, Daten "
                "oder Zulassungsdetails aus statischem Code nennen."
            ),
            "iemba": (
                "Die Kontextdatenbank ist momentan nicht verfuegbar. Ich kann deshalb keine "
                "aktuellen Fakten zum **IEMBA HSG** nachladen und sollte keine Preise, Daten "
                "oder Zulassungsdetails aus statischem Code nennen."
            ),
            "embax": (
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
        lang = language if language in ["en", "de"] else self._initial_language
        deterministic_routes = self._get_component(
            "_deterministic_routes", DeterministicRoutes
        )
        normalized_program = deterministic_routes._normalise_programme_id(program)
        property_filters = (
            {"programs": [normalized_program]} if normalized_program else None
        )
        try:
            response, _ = self._dbservice.query(
                query,
                lang,
                property_filters=property_filters,
                limit=config.get("TOP_K_RETRIEVAL"),
            )
            serialized = "\n\n".join(
                [doc.properties.get("body", "") for doc in response.objects]
            )
            return serialized
        except Exception as e:
            raise e

    @traceable(name="retrieve_context")
    def _retrieve_context_via_tool(
        self, query: str, program: str, language: str = None
    ) -> str:
        """Invoke the LangChain retrieval tool so deterministic fact paths are traceable."""
        retrieve_tool = getattr(self, "_retrieve_context_tool", None)
        if retrieve_tool is None:
            return self._retrieve_context(
                query=query, program=program, language=language
            )
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
            chain_logger.warning(
                "Subagents activated! This might lead to high response times!"
            )

        sub_provider = SubagentProvider(
            self._initial_language, self._query, self._retrieve_context
        )

        run_config: RunnableConfig = {"configurable": {"thread_id": 0}}
        fallback_middleware = ModelFallbackMiddleware(*modelconf.get_fallback_models())
        tool_retrieve_context = tool(
            name_or_callable="retrieve_context",
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
            "lead": create_agent(
                name="lead_agent",
                model=modelconf.get_main_agent_model(),
                tools=lead_agent_tools,
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(
                    "lead",
                    language=self._initial_language,
                    use_subagents=config.chain.ENABLE_SUBAGENTS,
                ),
                middleware=[
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                    fallback_middleware,
                ],
                context_schema=AgentContext,
                response_format=ProviderStrategy(StructuredAgentResponse),
            ),
        }
        if config.chain.ENABLE_SUBAGENTS:
            agents |= sub_provider.get_subagents(fallback_middleware)

        return agents, run_config

    def generate_greeting(self) -> str:
        greeting_message = random.choice(GREETING_MESSAGES[self._stored_language])
        return greeting_message

    def _query_lead(self, preprocessed_query: str) -> LeadAgentQueryResponse:
        """
        Phase 2: Execute agent.
        Takes the ALREADY validated query from the preprocessing phase.
        """
        # Reset redirect counters after a valid on-topic query reaches the agent.
        self._fallback_counters["scope_violations"] = {}

        response_language = self._stored_language
        deterministic_routes = self._get_component(
            "_deterministic_routes", DeterministicRoutes
        )
        conversation_state = self._get_component(
            "_conversation_state_manager", ConversationStateManager
        )
        deterministic_policy = getattr(
            self,
            "_deterministic_policy",
            DeterministicResponsePolicy.from_config(),
        )
        deterministic_control_enabled = deterministic_policy.control_enabled
        explicit_booking_intent = (
            deterministic_routes._is_explicit_booking_intent(preprocessed_query)
            if deterministic_control_enabled
            else False
        )
        booking_preference_follow_up = (
            deterministic_control_enabled
            and self._conversation_state.get("handover_requested") is True
            and deterministic_routes._previous_response_requested_booking_preferences()
            and deterministic_routes._is_booking_preference_follow_up(preprocessed_query)
        )

        # 1. History Update
        self._conversation_history.append(HumanMessage(preprocessed_query))

        # 2. System instruction
        language_instruction = SystemMessage(
            f"Respond in {get_language_name(response_language)} language."
        )

        # 3. Agent Call
        structured_response = self._query(
            agent=self._agents["lead"],
            messages=self._conversation_history + [language_instruction],
        )
        agent_response = structured_response.response
        additional_details = ResponseFormatter.clean_response(
            ResponseFormatter.remove_tables(
                structured_response.additional_details or ""
            )
        )
        chain_logger.info(
            f"Is answer context dependent: {structured_response.is_context_dependent}"
        )
        chain_logger.info(f"Additional details returned: {bool(additional_details)}")
        chain_logger.info(
            f"Appointment Requested: {structured_response.appointment_requested}"
        )
        chain_logger.info(
            f"Show Booking Widget: {structured_response.show_booking_widget}"
        )
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
            and not deterministic_routes._text_mentions_multiple_programmes(full_response)
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
            quality_evaluation = self._quality_handler.evaluate_response_quality(
                preprocessed_query, formatted_response
            )

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
            conversation_state._update_conversation_state(
                preprocessed_query, history_response
            )

            message_count = len(
                [m for m in self._conversation_history if isinstance(m, HumanMessage)]
            )
            if message_count % 5 == 0 or self._conversation_state.get(
                "suggested_program"
            ):
                conversation_state._log_user_profile()

        formatted_response = ResponseFormatter.format_name_of_university(
            formatted_response,
            language=response_language,
        )

        if deterministic_control_enabled:
            booking_flow_requested = (
                explicit_booking_intent or booking_preference_follow_up
            )
            appointment_requested = bool(booking_flow_requested)
            show_booking_widget = bool(
                booking_flow_requested
                and (
                    structured_response.show_booking_widget
                    or deterministic_routes._response_commits_to_showing_booking_widget(
                        formatted_response
                    )
                )
            )

            if structured_response.appointment_requested and not booking_flow_requested:
                chain_logger.info(
                    "Suppressed booking state because no explicit booking intent was detected."
                )
            elif booking_preference_follow_up and show_booking_widget:
                chain_logger.info(
                    "Continuing active booking flow and showing booking widget for a preference follow-up."
                )
        else:
            appointment_requested = bool(structured_response.appointment_requested)
            show_booking_widget = bool(structured_response.show_booking_widget)

        return LeadAgentQueryResponse(
            response=formatted_response,
            additional_details=additional_details,
            language=response_language,
            confidence_fallback=confidence_fallback,
            should_cache=False
            if (
                confidence_fallback
                or appointment_requested
                or structured_response.is_context_dependent
            )
            else True,
            processed_query=preprocessed_query,
            appointment_requested=appointment_requested,
            show_booking_widget=show_booking_widget,
            relevant_programs=structured_response.relevant_programs,
        )

    def _query(
        self, agent, messages: list, thread_id: str = None
    ) -> StructuredAgentResponse:
        try:
            config = self._config.copy()
            config["configurable"]["thread_id"] = thread_id or self._user_id

            result: AIMessage = agent.invoke(
                {"messages": messages},
                config=config,
                context=AgentContext(agent_name=agent.name),
            )
            response = result.get(
                "structured_response",
                StructuredAgentResponse(
                    response=result["messages"][-1].text,
                ),
            )
            return response
        except Exception as e:
            error_msg = e.body["message"] if hasattr(e, "body") else str(e)
            chain_logger.error(f"Failed to invoke the agent: {error_msg}")
            return StructuredAgentResponse(
                response=QUERY_EXCEPTION_MESSAGE[self._stored_language],
            )
