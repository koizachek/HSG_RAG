from langchain.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from .middleware import AgentChainMiddleware as chainmdw
from .prompts import PromptConfigurator as promptconf
from .models import ModelConfigurator as modelconf
from .utilclasses import AgentContext, LeadInformationState

from ..utils.logging import get_logger 

logger = get_logger('chain.subagents')

class SubagentProvider():
    def __init__(self, language, query_method, context_retrieval_method) -> None:
        self._language = language
        self._query = query_method
        self._tool_retrieve_context = context_retrieval_method


    def get_subagents(self, fallback_middleware):
        agents = dict()
        tool_retrieve_context = tool(
            name_or_callable='retrieve_context',
            runnable=self._tool_retrieve_context,
            description=(
                "Retrieve current programme context from the vector database. "
                "Arguments: query, program, optional language."
            ),
            return_direct=False,
            parse_docstring=False,
        )
        for agent in ['emba', 'iemba', 'embax']:
            agents[agent] = create_agent(
                name=f"{agent}_agent",
                model=modelconf.get_subagent_model(),
                tools=[tool_retrieve_context],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(
                    agent, 
                    language=self._language
                ),
                middleware=[
                    fallback_middleware,
                    chainmdw.get_tool_wrapper(),
                    chainmdw.get_model_wrapper(),
                ],
                context_schema=AgentContext,
            )
        self._agents = agents
        return agents


    def get_subagent_tools(self):
        return [
            tool(
                name_or_callable='call_emba_agent',
                runnable=self._call_emba_agent,
                description="Call the EMBA HSG programme support agent.",
                return_direct=False,
                parse_docstring=False,
            ),
            tool(
                name_or_callable='call_iemba_agent',
                runnable=self._call_iemba_agent,
                description="Call the IEMBA HSG programme support agent.",
                return_direct=False,
                parse_docstring=False,
            ),
            tool(
                name_or_callable='call_embax_agent',
                runnable=self._call_embax_agent,
                description="Call the emba X programme support agent.",
                return_direct=False,
                parse_docstring=False,
            ),
        ]


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
        except Exception as e:
            logger.error(f"EMBA Agent error: {e}")
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
        except Exception as e:
            logger.error(f"IEMBA Agent error: {e}")
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
        except Exception as e:
            logger.error(f"emba X Agent error: {e}")
            raise RuntimeError("Unable to retrieve emba X information at this time.")
