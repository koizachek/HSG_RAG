from langchain.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import (
    HumanMessage, 
    AIMessage, 
    SystemMessage, 
)
from langchain.agents.middleware import ModelFallbackMiddleware


from src.database.weavservice import WeaviateService

from src.rag.utilclasses import *
from src.rag.middleware import AgentChainMiddleware as chainmdw
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf
from src.rag.input_handler import InputHandler
from src.rag.response_formatter import ResponseFormatter
from src.rag.scope_guardian import ScopeGuardian

from src.utils.lang import detect_language, get_language_name
from src.utils.logging import get_logger 
from config import (
    TOP_K_RETRIEVAL,
    LOCK_LANGUAGE_AFTER_FIRST_MESSAGE,
    TRACK_USER_PROFILE,
    ENABLE_RESPONSE_CHUNKING
)

chain_logger = get_logger('agent_chain')

class ExecutiveAgentChain:
    def __init__(self, language: str = 'en') -> None:
        self._initial_language = language
        self._language = language
        self._user_language = None  # Will be locked after first user message
        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agents()
        self._conversation_history = []
        
        # Initialize conversation state
        self._conversation_state: ConversationState = {
            'user_language': None,
            'user_name': None,
            'years_experience': None,
            'qualification_level': None,
            'program_interest': [],
            'topics_discussed': [],
            'preferences_known': False
        }
        
        # Track scope violations for escalation
        self._scope_violation_count = 0
        
        chain_logger.info(f"Initialized new Agent Chain for language '{language}'")


    def _retrieve_context(self, query: str, language: str = None):
        """
        Send the query to the vector database to retrieve additional information about the program.

        Args:
            query: Keywords depicting information you want to retrieve in the primary language. 
            language: Optional parameter (either 'en' for English language or 'de' for German language). This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language. Use this parameter only if there's not enough information in your main language.
        """
        lang = language or self._language
        try:
            response, _ = self._dbservice.query(
                query=query, 
                lang=lang, 
                limit=TOP_K_RETRIEVAL,
            )
            serialized = '\n\n'.join(
                ("Source: {source}\nPrograms: {programs}\nContent: {content}".format(
                    source=doc.properties.get('source', 'unknown'),
                    programs=', '.join(doc.properties.get('programs', 'unknown')),
                    content=doc.properties.get('body', ''))) 
                for doc in response.objects
            )
            return serialized
        except Exception as _:
            return ''
   

    def _call_emba_agent(self, query: str) -> str:
        """
        Invokes the EMBA support agent to retrieve more detailed information about the EMBA program.
        
        Args:
            query: Query to the EMBA support agent. Provide collected user data in the query if possible.
        """
        try:
            response = self._query(
                agent=self._agents['emba'], 
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return response
        except Exception as e:
            chain_logger.error(f"EMBA Agent error: {e}")
            return "Unable to retrieve EMBA information at this time."


    def _call_iemba_agent(self, query: str) -> str:
        """
        Invokes the IEMBA support agent to retrieve more detailed information about the IEMBA program.
        
        Args:
            query: Query to the IEMBA support agent. Provide collected user data in the query if possible.
        """
        try:
            response = self._query(
                agent=self._agents['iemba'], 
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return response
        except Exception as e:
            chain_logger.error(f"IEMBA Agent error: {e}")
            return "Unable to retrieve IEMBA information at this time."

    def _call_embax_agent(self, query: str) -> str:
        """
        Invokes the EMBA X support agent to retrieve more detailed information about the EMBA X program.
        
        Args:
            query: Query to the EMBA X support agent. Provide collected user data in the query if possible.
        """
        try:
            response = self._query(
                agent=self._agents['embax'], 
                messages=[HumanMessage(query)],
                thread_id=f"emba_{hash(query)}",
            )
            return response
        except Exception as e:
            chain_logger.error(f"EMBA X Agent error: {e}")
            return "Unable to retrieve EMBA X information at this time."

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
                name="Lead Agent",
                model=modelconf.get_main_agent_model(),
                tools=tools_agent_calling,
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt('lead', language=self._language),
                middleware=[
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                    fallback_middleware,
                ],
                context_schema=AgentContext,
            ),            
        }
        for agent in ['emba', 'iemba', 'embax']:
            agents[agent]=create_agent(
                name=f"{agent.upper()} Agent",
                model=modelconf.get_subagent_model(),
                tools=[tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(agent, language=self._language),
                middleware=[
                    fallback_middleware,
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                ],
                context_schema=AgentContext,
            )
        return agents, config
   

    def generate_greeting(self) -> str:
        self._conversation_history.extend([
            SystemMessage("Generate a short greeting message and introduce yourself. 30 words max."),
            SystemMessage(f"Respond in {get_language_name(self._language)} language."),
        ])
        response = self._query(
            agent=self._agents['lead'], 
            messages=self._conversation_history,
        )
        self._conversation_history.append(AIMessage(response))
        return response


    def query(self, query: str) -> str:
        """
        Process user query with input handling, scope checking, and response formatting.
        
        Args:
            query: User input
            
        Returns:
            Formatted response
        """
        # Step 1: Process input (handle numeric inputs, validation)
        processed_query, is_valid = InputHandler.process_input(
            query,
            [msg for msg in self._conversation_history if isinstance(msg, (HumanMessage, AIMessage))]
        )
        
        if not is_valid or not processed_query:
            chain_logger.warning(f"Invalid input received: '{query}'")
            return "I didn't quite understand that. Could you please rephrase your question?"
        
        # Log if input was interpreted
        if processed_query != query:
            chain_logger.info(f"Interpreted input '{query}' as '{processed_query}'")
        
        # Step 2: Lock language on first user message
        if LOCK_LANGUAGE_AFTER_FIRST_MESSAGE and self._user_language is None:
            self._user_language = detect_language(processed_query)
            self._conversation_state['user_language'] = self._user_language
            self._language = self._user_language
            chain_logger.info(f"Locked conversation language to '{self._user_language}'")
        
        # Use locked language or current language
        response_language = self._user_language or self._language
        
        # Step 3: Check scope before querying agent
        scope_type = ScopeGuardian.check_scope(processed_query, response_language)
        
        if scope_type != 'on_topic':
            chain_logger.info(f"Out-of-scope query detected: {scope_type}")
            self._scope_violation_count += 1
            
            # Check if should escalate
            should_escalate, escalation_type = ScopeGuardian.should_escalate(
                processed_query,
                scope_type,
                self._scope_violation_count
            )
            
            if should_escalate:
                redirect_msg = ScopeGuardian.get_escalation_message(
                    escalation_type,
                    response_language
                )
            else:
                redirect_msg = ScopeGuardian.get_redirect_message(
                    scope_type,
                    response_language
                )
            
            # Add to history
            self._conversation_history.append(HumanMessage(processed_query))
            self._conversation_history.append(AIMessage(redirect_msg))
            
            return redirect_msg
        
        # Reset violation count on valid topic
        self._scope_violation_count = 0
        
        # Step 4: Build messages with locked language
        self._conversation_history.append(HumanMessage(processed_query))
        
        # Add language instruction (use locked language)
        language_instruction = SystemMessage(
            f"Respond in {get_language_name(response_language)} language."
        )
        
        # Step 5: Query agent
        response = self._query(
            agent=self._agents['lead'],
            messages=self._conversation_history + [language_instruction],
        )
        
        # Step 6: Format response (remove tables, chunk if needed)
        if ENABLE_RESPONSE_CHUNKING:
            formatted_response = ResponseFormatter.format_response(
                response,
                agent_type='lead',
                enable_chunking=True
            )
        else:
            formatted_response = ResponseFormatter.remove_tables(response)
        
        # Clean up response
        formatted_response = ResponseFormatter.clean_response(formatted_response)
        
        # Add to history
        self._conversation_history.append(AIMessage(formatted_response))
        
        return formatted_response


    def _query(self, agent, messages: list, thread_id: str = None) -> str:
        try:
            config = self._config.copy()
            config['configurable']['thread_id'] = thread_id or 0
                
            result: AIMessage = agent.invoke(
                {"messages": messages},
                config=config,
                context=AgentContext(agent_name=agent.name),
            )
            response = result['messages'][-1]
            return response.text
        except Exception as e:
            error_msg = e.body['message'] if hasattr(e, 'body') else str(e)
            chain_logger.error(f"Failed to invoke the agent: {error_msg}")
            return "I'm sorry, I cannot provide a helpful response right now. Please contact tech support or try again later."
