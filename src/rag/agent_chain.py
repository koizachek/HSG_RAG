from langchain.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import (
    HumanMessage, 
    AIMessage, 
    SystemMessage, 
)
from langchain.agents.middleware import (
    SummarizationMiddleware,
    ModelFallbackMiddleware,
)

from langgraph.checkpoint.memory import InMemorySaver

from src.database.weavservice import WeaviateService

from src.rag.utilclasses import *
from src.rag.middleware import AgentChainMiddleware as chainmdw
from src.rag.prompts import PromptConfigurator as promptconf
from src.rag.models import ModelConfigurator as modelconf

from src.utils.logging import get_logger 
from config import TOP_K_RETRIEVAL

chain_logger = get_logger('agent_chain')

class ExecutiveAgentChain:
    def __init__(self, language: str = 'en') -> None:
        self._language = language 
        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agents()
        chain_logger.info(f"Initalized new Agent Chain for language '{language}'")


    def _retrieve_context(self, query: str, language: str = None):
        """
        Send the query to the vector database to retrieve additional information about the program.

        Args:
            query: Keywords depicting information you want to retrieve in the primary language. 
            language: Optional parameter (either 'en' for English language or 'de' for German language). This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language. Use this parameter only if there's not enough information in your main language.
        """
        print('called retrieve_context')
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
        response = self._query(agent=self._agents['emba'], messages=[HumanMessage(query)])
        return response
    

    def _call_iemba_agent(self, query: str) -> str:
        """
        Invokes the IEMBA support agent to retrieve more detailed information about the IEMBA program.
        
        Args:
            query: Query to the IEMBA support agent. Provide collected user data in the query if possible.
        """
        response = self._query(agent=self._agents['iemba'], messages=[HumanMessage(query)])
        return response


    def _call_embax_agent(self, query: str) -> str:
        """
        Invokes the EMBA X support agent to retrieve more detailed information about the EMBA X program.
        
        Args:
            query: Query to the EMBA X support agent. Provide collected user data in the query if possible.
        """
        response = self._query(agent=self._agents['embax'], messages=[HumanMessage(query)])
        return response


    def _init_agents(self):
        config: RunnableConfig = {
            'configurable': {'thread_id': 0}
        }
        checkpointer = InMemorySaver()
        fallback_middleware = ModelFallbackMiddleware(
            *modelconf.get_fallback_models()
        )
        summarization_middleware = SummarizationMiddleware(
            model=modelconf.get_summarization_model(),
            max_tokens_before_summary=1000,
            messages_to_keep=5,
            summary_prompt=promptconf.get_summarization_prompt(),
            summary_prefix=promptconf.get_summary_prefix(),
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
                tools=tools_agent_calling + [tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt('lead', language=self._language),
                middleware=[
                    fallback_middleware,
                    summarization_middleware,
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                ],
                checkpointer=checkpointer,
                context_schema=AgentContext,
            ),            
        }
        for agent in ['emba', 'iemba', 'embax']:
            agents[agent]=create_agent(
                name=f"{agent.upper()} Agent",
                model=modelconf.get_main_agent_model(),
                tools=[tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(agent, language=self._language),
                middleware=[
                    fallback_middleware,
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                ],
                checkpointer=checkpointer,
                context_schema=AgentContext,
            )
        return agents, config
   

    def generate_greeting(self) -> str:
        return self._query(
            agent=self._agents['lead'], 
            messages=[SystemMessage("Generate a greeting message and introduce yourself.")],
        ) 


    def query(self, query: str) -> str:
        return self._query(
            agent=self._agents['lead'],
            messages=[HumanMessage(query), SystemMessage("You MUST call the retrieve_context tool before answering!")],
        )


    def _query(self, agent, messages: list) -> str:
        try:
            result: AIMessage = agent.invoke(
                {"messages": messages},
                config=self._config,
                context=AgentContext(agent_name=agent.name),
            )
            response = result['messages'][-1]
            return response.text
        except Exception as e:
            chain_logger.error(f"Failed to invoke the agent: {e.body['message']}")
            return "I'm sorry, I cannot provide a helpful response right now. Please contact the tech support or try again later."
