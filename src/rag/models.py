from langchain.chat_models import BaseChatModel
from config import LLMProvider, LLMProviderConfiguration as llmconf

from src.utils.logging import get_logger

logger = get_logger("model_config")

class ModelConfigurator:
    _main_model_instance: BaseChatModel = None
    _fallback_models_instances: list[BaseChatModel] = None
    _summarization_model_instance: BaseChatModel = None
    

    @classmethod
    def get_summarization_model(cls) -> BaseChatModel:
        if cls._summarization_model_instance:
            return cls._summarization_model_instance
        
        try:
            # Add custom summarization model initialization here if needed
            cls._summarization_model_instance = cls.get_main_agent_model()
            logger.info(f"Initialized summarization model '{llmconf.LLM_PROVIDER.name}:{llmconf.get_default_model()}'")
            return cls._summarization_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize the summarization model: {e}")
            raise e


    @classmethod
    def get_main_agent_model(cls) -> BaseChatModel:
        """Initialize the language model based on config."""
        if cls._main_model_instance:
            return cls._main_model_instance

        try:
            cls._main_model_instance = cls._initialize_model(
                provider=llmconf.LLM_PROVIDER,
                model=llmconf.get_default_model()
            )
            logger.info(f"Initialized main agent model '{llmconf.LLM_PROVIDER.name}:{llmconf.get_default_model()}'")
            return cls._main_model_instance
        except Exception as e: 
            logger.error(f"Failed to initialize the main agent model for provider '{llmconf.LLM_PROVIDER.name}': {e}")
            raise e


    @classmethod
    def get_fallback_models(cls) -> list[BaseChatModel]:
        if cls._fallback_models_instances != None:
            return cls._fallback_models_instances 

        cls._fallback_models_instances = cls._initialize_fallback_models()
        if len(cls._fallback_models_instances) == 0:
            logger.warning("No fallback models were initialized! Response generation may result in unexpected errors!")
        return cls._fallback_models_instances


    @classmethod
    def _initialize_fallback_models(cls) -> list[BaseChatModel]:
        fallback_models_instances = []
        for fallback_provider, fallback_model in llmconf.get_fallback_models().items():
            try:
                fallback_model_instance = cls._initialize_model(
                    provider=fallback_provider,
                    model=fallback_model,
                )
                logger.info(f"Initialized fallback model '{fallback_provider.name}:{fallback_model}'")
                fallback_models_instances.append(fallback_model_instance)
            except Exception as e:
                logger.error(f"Failed to initialize the fallback model {fallback_provider.name}:{fallback_model}: {e}; skipping...")
        return fallback_models_instances


    @classmethod
    def _initialize_model(cls, provider: LLMProvider, model: str) -> BaseChatModel:
        try:
            match provider.name:
                case 'groq':
                    from langchain_groq import ChatGroq
                    return ChatGroq(
                        model=model,
                        groq_api_key=llmconf.get_api_key(),
                        temperature=0.01,
                    )
                case (  'open_router:openai' 
                      | 'open_router:alibaba' 
                      | 'open_router:nvidia'
                      | 'open_router:meituan'):
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=model,
                        base_url=llmconf.OPEN_ROUTER_BASE_URL,
                        api_key=llmconf.get_api_key(),
                        temperature=0.01,
                    )
                case 'open_router:deepseek':
                    from langchain_deepseek import ChatDeepSeek
                    return ChatDeepSeek(
                        model=model,
                        api_key=llmconf.OPEN_ROUTER_API_KEY,
                        api_base=llmconf.OPEN_ROUTER_BASE_URL,
                    )
                case 'openai':
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=model,
                        openai_api_key=llmconf.get_api_key(),
                        max_tokens=1000,
                        temperature=0.01,
                    )
                case 'ollama':
                    from langchain_ollama import ChatOllama
                    return ChatOllama(
                        model=model,
                        base_url=llmconf.OLLAMA_BASE_URL,
                        temperature=0.01,
                        reasoning=llmconf.get_reasoning_support(),
                        num_predict=2048,
                    )
                case _:
                    raise ValueError(f"Unsupported LLM provider: {provider.name}")
        except Exception as e:
            raise e
