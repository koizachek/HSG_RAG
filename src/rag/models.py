from langchain.chat_models import BaseChatModel
from src.config import config

from src.utils.logging import get_logger

logger = get_logger("model_config")

class ModelConfigurator:
    _main_model_instance: BaseChatModel = None
    _subagent_model_instance: BaseChatModel = None
    _fallback_models_instances: list[BaseChatModel] = None
    _summarization_model_instance: BaseChatModel = None
    _confidence_scoring_model_instance: BaseChatModel = None 
    _language_detector_model_instance: BaseChatModel = None
    
    @classmethod 
    def get_language_detector_model(cls) -> BaseChatModel:
        if cls._language_detector_model_instance:
            return cls._language_detector_model_instance
        provider, model = config.llm.LANGUAGE_DETECTION_MODEL
        try:
            cls._language_detector_model_instance = cls._initialize_model(
                provider=provider,
                model=model,
                role="language_detector",
            )
            logger.info(f"Initialized language detection model '{provider}:{model}'")
            return cls._language_detector_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize language detection model '{provider}:{model}': {e}")
            raise e

    @classmethod
    def get_confidence_scoring_model(cls) -> BaseChatModel:
        if cls._confidence_scoring_model_instance:
            return cls._confidence_scoring_model_instance
        provider, model = config.llm.CONFIDENCE_SCORING_MODEL
        try:
            cls._confidence_scoring_model_instance = cls._initialize_model(
                provider=provider,
                model=model,
                role="confidence_scoring",
            )
            logger.info(f"Initialized confidence scoring model '{provider}:{model}'")
            return cls._confidence_scoring_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize confidence scoring model '{provider}:{model}': {e}")
            raise e


    @classmethod
    def get_summarization_model(cls) -> BaseChatModel:
        if cls._summarization_model_instance:
            return cls._summarization_model_instance
        provider, model = config.llm.SUMMARIZATION_MODEL
        try:
            cls._summarization_model_instance = cls._initialize_model(
                provider=provider,
                model=model,
                role="main",
            )
            logger.info(f"Initialized summarization model '{provider}:{model}'")
            return cls._summarization_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize summarization model '{provider}:{model}': {e}")
            raise e


    @classmethod
    def get_subagent_model(cls) -> BaseChatModel:
        if cls._subagent_model_instance:
            return cls._subagent_model_instance
        provider, model = config.llm.SUBAGENT_MODEL
        try:
            cls._subagent_model_instance = cls._initialize_model(
                provider=provider,
                model=model,
                role="main",
            )
            logger.info(f"Initialized subagent model '{provider}:{model}'")
            return cls._subagent_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize subagent model '{provider}:{model}': {e}")
            raise e

    @classmethod
    def get_main_agent_model(cls) -> BaseChatModel:
        """Initialize the language model based on config."""
        if cls._main_model_instance:
            return cls._main_model_instance
        provider, model = config.llm.MAIN_AGENT_MODEL
        try:
            cls._main_model_instance = cls._initialize_model(
                provider=provider,
                model=model,
                role="main",
            )
            logger.info(f"Initialized main agent model '{provider}:{model}'")
            return cls._main_model_instance
        except Exception as e: 
            logger.error(f"Failed to initialize the main agent model '{provider}:{model}': {e}")
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
        for fallback_provider, fallback_model in config.llm.FALLBACK_MODELS:
            try:
                fallback_model_instance = cls._initialize_model(
                    provider=fallback_provider,
                    model=fallback_model,
                    role="main",
                )
                logger.info(f"Initialized fallback model '{fallback_provider}:{fallback_model}'")
                fallback_models_instances.append(fallback_model_instance)
            except Exception as e:
                logger.error(f"Failed to initialize the fallback model {fallback_provider}:{fallback_model}: {e}; skipping...")
        return fallback_models_instances


    @classmethod
    def _initialize_model(cls, provider, model: str, role: str = "main") -> BaseChatModel:
        provider_name = cls._provider_name(provider)
        try:
            match provider_name:
                case 'huggingface':
                    from langchain_huggingface import (
                        ChatHuggingFace,
                        HuggingFaceEndpoint,
                    )
                    llm = HuggingFaceEndpoint(
                        repo_id=model,
                        provider='featherless-ai',
                        task='text-generation',
                        max_new_tokens=3072,
                        temperature=0.1,
                        timeout=60,
                        huggingfacehub_api_token=config.llm.HUGGING_FACE_API_KEY,
                    )
                    return ChatHuggingFace(llm=llm)
                case 'groq':
                    from langchain_groq import ChatGroq
                    return ChatGroq(
                        model=model,
                        groq_api_key=config.llm.get_api_key(provider_name),
                        temperature=0.01,
                    )
                case (  'open_router:openai' 
                      | 'open_router:alibaba' 
                      | 'open_router:nvidia'
                      | 'open_router:meituan'):
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=model,
                        base_url=config.llm.OPEN_ROUTER_BASE_URL,
                        api_key=config.llm.get_api_key(provider_name),
                        temperature=0.01,
                    )
                case 'open_router:deepseek':
                    from langchain_deepseek import ChatDeepSeek
                    return ChatDeepSeek(
                        model=model,
                        api_key=config.llm.get_api_key(provider_name),
                        api_base=config.llm.OPEN_ROUTER_BASE_URL,
                    )
                case 'openai':
                    budget = cls._openai_budget(role)
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=model,
                        openai_api_key=config.llm.get_api_key(provider_name),
                        max_tokens=budget["max_tokens"],
                        temperature=0.01,
                        # Latency fix: 60s timeout x retries x fallbacks
                        # multiplied worst-case latency into minutes
                        timeout=budget["timeout"],
                        request_timeout=budget["request_timeout"],
                    )
                case 'ollama':
                    from langchain_ollama import ChatOllama
                    return ChatOllama(
                        model=model,
                        base_url=config.llm.OLLAMA_BASE_URL,
                        temperature=0.01,
                        reasoning=config.llm.get_reasoning_support(provider_name),
                        num_predict=2048,
                    )
                case _:
                    raise ValueError(f"Unsupported LLM provider: {provider_name}")
        except Exception as e:
            raise e


    @staticmethod
    def _provider_name(provider) -> str:
        return provider.name if hasattr(provider, "name") else str(provider)


    @staticmethod
    def _openai_budget(role: str) -> dict[str, int]:
        match role:
            case "language_detector":
                return {"max_tokens": 64, "timeout": 10, "request_timeout": 10}
            case "confidence_scoring":
                return {"max_tokens": 3072, "timeout": 60, "request_timeout": 60}
            case _:
                return {"max_tokens": 3072, "timeout": 30, "request_timeout": 30}
