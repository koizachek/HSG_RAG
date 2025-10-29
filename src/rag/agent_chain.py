from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import SummarizationMiddleware
from langchain.tools import tool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage

from langgraph.checkpoint.memory import InMemorySaver

from typing_extensions import TypedDict

from src.database.weavservice import WeaviateService
from src.utils.logging import get_logger 
from src.rag.prompts import get_configured_agent_prompt
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
        self._agent, self._config = self._init_agent()
        chain_logger.info(f"Initalized new Agent Chain for language '{language}'")

    
    def _retrieve_context(self, query: str):
        """
        This tool can be used by the agent to retrieve additional context from the database.
        """
        chain_logger.info("Agent is retrieving documents from the database...")
        chain_logger.info(f"Retrieval query: {query}")
        try:
            response, _ = self._dbservice.query(
                query=query, 
                lang=self._language, 
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
    

    def _init_agent(self):
        config: RunnableConfig = {
            'configurable': {'thread_id': 0}
        }
        agent = create_agent(
            model=self._get_agent_model(),
            tools=self._init_agent_tools(),
            state_schema=LeadInformationState,
            system_prompt=get_configured_agent_prompt(self._language),
            checkpointer=InMemorySaver(),
            middleware=[
                SummarizationMiddleware(
                    model=self._get_summarization_model(),
                    max_tokens_before_summary=1000,
                    messages_to_keep=20,
                ),
            ],
        )

        return agent, config
   

    def _init_agent_tools(self):
        return [
            tool(self._retrieve_context)
        ]

    def _get_summarization_model(self) -> BaseChatModel:
        # TODO: Find less powerful and quick alternatives to accompany the main models
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


    def _query(self, messages: list) -> str:
        try:
            result: AIMessage = self._agent.invoke(
                {"messages": messages},
                config=self._config,
            )
            return result['messages'][-1].text
        except Exception as e:
            chain_logger.error(f"Failed to generate a greeting message: {e}")
            return "I'm sorry, I cannot provide a helpful response right now. Please contact the tech support or try again later."
