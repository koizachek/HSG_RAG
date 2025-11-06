from langchain.tools import tool
from langchain.tools.tool_node import ToolCallRequest
from langchain.chat_models import BaseChatModel
from langchain.agents.middleware import (
        ModelRequest,

        wrap_model_call,
        wrap_tool_call,
)
from openai import (
    OpenAIError, 
    InternalServerError, 
    NotFoundError, 
    RateLimitError,
)

from config import MAX_MODEL_RETRIES
from src.rag.utilclasses import AgentContext
from src.utils.logging import get_logger

model_logger = get_logger('chain_model_call')
tool_logger  = get_logger('chain_tool_call')

class AgentChainMiddleware:
    _tool_wrapper_middleware = None 
    _model_wrapper_middleware = None


    @classmethod 
    def get_tool_wrapper(cls):
        if cls._tool_wrapper_middleware:
            return cls._tool_wrapper_middleware

        cls._tool_wrapper_middleware = wrap_tool_call(cls._tool_call_wrapper)
        tool_logger.info(f"Initialized tool call wrapper")
        return cls._tool_wrapper_middleware

    
    @classmethod
    def get_model_wrapper(cls):
        if cls._model_wrapper_middleware:
            return cls._model_wrapper_middleware

        cls._model_wrapper_middleware = wrap_model_call(cls._model_call_wrapper)
        model_logger.info(f"Initialized model call wrapper with maximum of {MAX_MODEL_RETRIES} retry attempts")
        return cls._model_wrapper_middleware


    @staticmethod
    def _model_call_wrapper(request: ModelRequest, handler):
        context: AgentContext  = request.runtime.context
        model:   BaseChatModel = request.model
        model_logger.info(f"{context.agent_name} is attempting to call model '{model.model_name}'...")
        for attempt in range(1, MAX_MODEL_RETRIES+1):
            try:
                result = handler(request)
                model_logger.info(f"Recieved response from model after {attempt} attempt{'s' if attempt > 1 else ''}")
                return result
            except OpenAIError as e:
                match e:
                    case InternalServerError():
                        model_logger.warning(f"[{e.code}] Internal difficulties on the provider side, retrying the call...")
                    case RateLimitError():
                        model_logger.warning(f"[{e.code}] Model is temporary rate limited, retrying the call...")
                    case NotFoundError():
                        model_logger.error(f"[{e.code}] Model cannot be used in the chain, reason: {e.body['message']}")
                        raise e

                if attempt == MAX_MODEL_RETRIES:
                    model_logger.warning(f"Failed to recieve response from model '{model.model_name}' after {MAX_MODEL_RETRIES} attempt{'s' if attempt > 1 else ''}, reason: {e.body['message']}")
                    model_logger.info(f"Switching to the fallback model...")
                    raise e


    @staticmethod
    def _tool_call_wrapper(request: ToolCallRequest, handler):
        try:
            context: AgentContext = request.runtime.context or AgentContext(agent_name="Agent")
            tool_call = request.tool_call 
            try:
                tool_logger.info(f"{context.agent_name} is attempting to use tool '{tool_call['name']}'...")
                result = handler(request)
                tool_logger.info(f"Tool use successfull, returning the result...")
                return result
            except Exception as e:
                tool_logger.error(f"Error in the tool call wrapper: {e}")
                raise e
        except Exception as e:
            tool_logger.error(f"COMPLETELY UNEXPECTED ERROR!!!: {e}")

