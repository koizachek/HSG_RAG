from langchain.chat_models import BaseChatModel
from ..config import config

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
            cls._language_detector_model_instance = cls._initialize_model(provider, model)
            logger.info(f"Initialized language detection model: '{provider}:{model}'")
            return cls._language_detector_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize the language detection model '{provider}:{model}': {e}")
            raise e


    @classmethod
    def get_confidence_scoring_model(cls) -> BaseChatModel:
        if cls._confidence_scoring_model_instance:
            return cls._confidence_scoring_model_instance

        provider, model = config.llm.CONFIDENCE_SCORING_MODEL
        try:
            cls._confidence_scoring_model_instance = cls._initialize_model(provider, model)
            logger.info(f"Initialized confidence scoring model: '{provider}:{model}'")
            return cls._confidence_scoring_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize the confidence scoring model '{provider}:{model}': {e}")
            raise e


    @classmethod
    def get_summarization_model(cls) -> BaseChatModel:
        if cls._summarization_model_instance:
            return cls._summarization_model_instance   

        provider, model = config.llm.SUMMARIZATION_MODEL
        try:
            cls._summarization_model_instance = cls._initialize_model(provider, model)
            logger.info(f"Initialized summarization model: '{provider}:{model}'")
            return cls._summarization_model_instance
        except Exception as e:
            logger.error(f"Failed to initialize the summarization model '{provider}:{model}': {e}")
            raise e

    @classmethod
    def get_subagent_model(cls) -> BaseChatModel:
        if cls._subagent_model_instance:
            return cls._subagent_model_instance
        
        provider, model = config.llm.SUBAGENT_MODEL
        try:
            cls._subagent_model_instance = cls._initialize_model(provider, model)
            logger.info(f"Initialized subagent model: '{provider}:{model}'")
            return cls._subagent_model_instance
        except Exception as e: 
            logger.error(f"Failed to initialize the subagent_model '{provider}:{model}': {e}")


    @classmethod
    def get_main_agent_model(cls) -> BaseChatModel:
        """Initialize the language model based on config."""
        if cls._main_model_instance:
            return cls._main_model_instance
        
        provider, model = config.llm.MAIN_AGENT_MODEL
        try:
            cls._main_model_instance = cls._initialize_model(provider, model)
            logger.info(f"Initialized main agent model: '{provider}:{model}'")
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
        for fallback_model in config.llm.FALLBACK_MODELS:
            provider, model = fallback_model
            try:
                fallback_model_instance = cls._initialize_model(provider, model)
                logger.info(f"Initialized fallback model: '{provider}:{model}'")
                fallback_models_instances.append(fallback_model_instance)
            except Exception as e:
                logger.error(f"Failed to initialize the fallback model {provider}:{model}: {e}; skipping...")
        return fallback_models_instances


    @classmethod
    def _initialize_model(cls, provider: str, model: str) -> BaseChatModel:
        try:
            match provider: 
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
                    chat_model = ChatHuggingFace(llm=llm)
                    return chat_model
                case 'groq':
                    from langchain_groq import ChatGroq
                    return ChatGroq(
                        model=model,
                        groq_api_key=config.llm.GROQ_API_KEY,
                        temperature=0.01,
                    )
                case (  'open_router:openai' 
                      | 'open_router:alibaba' 
                      | 'open_router:nvidia'
                      | 'open_router:meituan'):
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=model,
                        base_url=config.llm.OPENROUTER_BASE_URL,
                        api_key=config.llm.OPENROUTER_API_KEY,
                        temperature=0.01,
                        
                    )
                case 'open_router:deepseek':
                    from langchain_deepseek import ChatDeepSeek
                    return ChatDeepSeek(
                        model=model,
                        api_key=config.llm.OPENROUTER_API_KEY,
                        api_base=config.llm.OPENROUTER_BASE_URL,
                    )
                case 'openai':
                    from langchain_openai import ChatOpenAI
                    return ChatOpenAI(
                        model=model,
                        openai_api_key=config.llm.OPENAI_API_KEY,
                        max_tokens=3072,
                        temperature=0.01,
                        timeout=60,
                        request_timeout=60,
                    )
                case 'ollama':
                    from langchain_ollama import ChatOllama
                    return ChatOllama(
                        model=model,
                        base_url=config.llm.OLLAMA_BASE_URL,
                        temperature=0.01,
                        reasoning=False,
                        num_predict=2048,
                    )
                case _:
                    raise ValueError(f"Unsupported LLM provider: {provider}")
        except Exception as e:
            raise e
