from langchain.agents import create_agent, AgentState
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
        HumanMessage, 
        AIMessage, 
        SystemMessage, 
        AnyMessage,
)
from langchain.agents.middleware import (
        SummarizationMiddleware,
        ToolCallLimitMiddleware,
)

from typing_extensions import TypedDict

from src.database.weavservice import WeaviateService
from src.utils.logging import get_logger 
from src.rag.prompts import PromptConfigurator as promptconf
from config import LLMProviderConfiguration as llmconf, TOP_K_RETRIEVAL

chain_logger = get_logger('agent_chain')


class State(TypedDict):
    messages: list[AnyMessage]
    answer: str


class LeadInformationState(AgentState):
    lead_name: str
    lead_age:  int
    lead_language_knowledge: list 
    lead_work_experience: dict
    lead_motivation: list


class ExecutiveAgentChain:
    def __init__(self, language: str = 'en') -> None:
        self._language = language 
        self._dbservice = WeaviateService()
        self._agents, self._config = self._init_agent()
        chain_logger.info(f"Initalized new Agent Chain for language '{language}'")

    
    def _retrieve_context(self, query: str, language: str = None):
        """
        Send the query to the vector database to retrieve addition information about the program.

        Args:
            query: Keywords depicting information you want to retrieve 
            language: Optional parameter (either 'en' for English language or 'de' for German language). This parameter selects the language of the database to query from. The input query must be written in the same language as the selected language. Use this parameter only if there's not enough information in your main language.
        """ 
        lang = language or self._language
        chain_logger.info("Agent is retrieving documents from the database...")
        chain_logger.info(f"Retrieval query: {query}")
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
            chain_logger.info("Retrieval from the database finished successfully")
            return serialized
        except Exception as e:
            chain_logger.error(f"Agent failed to retrieve documents from the database: {e}")
            return ""
   

    def _call_emba_agent(self, query: str) -> str:
        """
        Invokes the EMBA support agent to retrieve more detailed information about the EMBA program.
        
        Args:
            query: Query to the EMBA support agent. Provide collected user data in the query if possible.
        """
        chain_logger.info("Lead agent called the EMBA agent")
        chain_logger.info(f"Lead query: {query}")
        response = self._query(agent=self._agents['emba'], messages=[HumanMessage(query)])
        chain_logger.info(f"EMBA agent response: {response}")
        return response
    

    def _call_iemba_agent(self, query: str) -> str:
        """
        Invokes the IEMBA support agent to retrieve more detailed information about the IEMBA program.
        
        Args:
            query: Query to the IEMBA support agent. Provide collected user data in the query if possible.
        """
        chain_logger.info("Lead agent called the IEMBA agent") 
        chain_logger.info(f"Lead query: {query}")
        response = self._query(agent=self._agents['iemba'], messages=[HumanMessage(query)])
        chain_logger.info(f"IEMBA agent response: {response}")
        return response


    def _call_embax_agent(self, query: str) -> str:
        """
        Invokes the EMBA X support agent to retrieve more detailed information about the EMBA X program.
        
        Args:
            query: Query to the EMBA X support agent. Provide collected user data in the query if possible.
        """
        chain_logger.info("Lead agent called the EMBA X agent") 
        chain_logger.info(f"Lead query: {query}")
        response = self._query(agent=self._agents['embax'], messages=[HumanMessage(query)])
        chain_logger.info(f"EMBA X agent response: {response}")
        return response


    def _init_agent(self):
        config: RunnableConfig = {
            'configurable': {'thread_id': 0}
        }
        summarization_middleware = SummarizationMiddleware(
            model=self._get_summarization_model(),
            max_tokens_before_summary=1000,
            messages_to_keep=5,
            summary_prompt=promptconf.get_summarization_prompt(),
            summary_prefix=promptconf.get_summary_prefix(),
        )
        tool_call_limiter_middleware = ToolCallLimitMiddleware(
            run_limit=1
        )
        agents = {
            'lead': create_agent(
                model=self._get_agent_model(),
                tools=[
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
                ],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt('lead', language=self._language),
                middleware=[
                    summarization_middleware, 
                    tool_call_limiter_middleware,
                ]),
        }
        for agent in ['emba', 'iemba', 'embax']:
            agents[agent]=create_agent(
                model=self._get_agent_model(),
                tools=[
                    tool(
                        name_or_callable='retrieve_context',
                        runnable=self._retrieve_context,
                        return_direct=False,
                        parse_docstring=True,
                    )
                ],
                state_schema=LeadInformationState,
                system_prompt=promptconf.get_configured_agent_prompt(agent, language=self._language),
                middleware=[tool_call_limiter_middleware],
            )    

        return agents, config
   



    def _get_summarization_model(self) -> BaseChatModel:
        return self._get_agent_model()


    def _get_agent_model(self) -> BaseChatModel:
        """Initialize the language model based on config."""
        try:
            match llmconf.LLM_PROVIDER:
                case 'groq':
                    from langchain_groq import ChatGroq
                    return ChatGroq(
                        model=llmconf.get_default_model(),
                        groq_api_key=llmconf.get_api_key(),
                        temperature=0.2,
                    )
                case 'open_router':
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=llmconf.get_default_model(),
                        base_url="https://openrouter.ai/api/v1",
                        api_key=llmconf.get_api_key(),
                        temperature=0.2,
                    )
                case 'openai':
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=llmconf.get_default_model(),
                        openai_api_key=llmconf.get_api_key(),
                        max_tokens=1000,
                        temperature=0.2,
                    )
                case 'ollama':
                    from langchain_ollama import ChatOllama
                    return ChatOllama(
                        model=llmconf.get_default_model(),
                        base_url=llmconf.OLLAMA_BASE_URL,
                        temperature=0.2,
                        reasoning=llmconf.get_reasoning_support(),
                        num_predict=2048,
                    )
                case _:
                    chain_logger.error(f"Unsupported LLM provider: {llconf.LLM_PROVIDER}")
                    raise ValueError(f"Unsupported LLM provider: {llmconf.LLM_PROVIDER}")
        except Exception as e:
            chain_logger.error(f"Failed to initiate the LLM model: {e}")
            raise e
   

    def generate_greeting(self) -> str:
        return self._query([SystemMessage("Generate a greeting message and introduce yourself.")]) 


    def query(self, query: str) -> str:
        return self._query([HumanMessage(query)])


    def _query(self, messages: list, agent=None) -> str:
        try:
            call_agent = agent or self._agents['lead']
            result: AIMessage = call_agent.invoke(
                {"messages": messages},
                config=self._config,
            )
            return result['messages'][-1].text
        except Exception as e:
            chain_logger.error(f"Failed to generate a greeting message: {e}")
            return "I'm sorry, I cannot provide a helpful response right now. Please contact the tech support or try again later."
