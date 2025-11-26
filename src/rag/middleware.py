from datetime import datetime
from langchain.tools.tool_node import ToolCallRequest
from langchain.chat_models import BaseChatModel
from langchain.agents.middleware import (
        ModelRequest,
        ModelResponse,

        wrap_model_call,
        wrap_tool_call,
)
from langchain_core.messages import ToolMessage
from openai import (
    BadRequestError,
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
        tool_logger.info(f"Initialized tool call wrapper with call inspection")
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
                response: ModelResponse = handler(request)
                model_logger.info(f"{context.agent_name} recieved response from model after {attempt} attempt{'s' if attempt > 1 else ''}")
                result = response.result[0]
                metadata = result.response_metadata
                # Check if any errors occured during tool call execution.
                # Some errors might be fatal, making the model unusable in the agent chain
                if hasattr(result, 'invalid_tool_calls') and result.invalid_tool_calls:
                    for invalid_call in result.invalid_tool_calls:
                        fail_reason = invalid_call.get('error', 'Unknown').replace('\n', '')
                        model_logger.warning(f"Failed tool call: {invalid_call['name']}, error: {fail_reason}, retrying the call...")
                        if 'JSONDecodeError' in fail_reason:
                            model_logger.error(f"Model does not support current tool call architecture! Switching to the fallback model...")
                            raise Exception("Unsupported model") 
                elif not result.content and metadata['finish_reason'] != 'tool_calls':
                    model_logger.warning(f"Model returned an empty response, reason - {metadata['finish_reason']}! Retrying the call...")
                else:
                    return response
            except OpenAIError as e:
                match e:
                    case InternalServerError():
                        model_logger.warning(f"[{e.code}] Internal difficulties on the provider side, retrying the call...")
                    case RateLimitError():
                        model_logger.warning(f"[{e.code}] Model is temporary rate limited, retrying the call...")
                    case NotFoundError():
                        model_logger.error(f"[{e.code}] Model cannot be used in the chain, reason: {e.body['message']}")
                        raise e
                    case BadRequestError():
                        model_logger.error(f"[400] Bad request: {e.body['message']}")
                        raise e

                if attempt == MAX_MODEL_RETRIES:
                    model_logger.warning(f"Failed to recieve response from model '{model.model_name}' after {MAX_MODEL_RETRIES} attempt{'s' if attempt > 1 else ''}, reason: {e.body['message']}")
                    model_logger.info(f"Switching to the fallback model...")
                    raise e
            except Exception as e:
                model_logger.error(f"An error occured during model call (possibly backend side): {e}")
                raise e
        
        errormsg = f"{context.agent_name} failed to perform the model call due to unknown reason!"
        model_logger.error(errormsg)
        raise RuntimeError(errormsg)


    @staticmethod
    def _tool_call_wrapper(request: ToolCallRequest, handler):
        context: AgentContext = request.runtime.context or AgentContext(agent_name="Agent")
        
        tool_call = request.tool_call
        tool_logger.info(f"{context.agent_name} is calling tool: {tool_call['name']} with tool call id {tool_call['id']}")
        try:
            response = handler(request)
            tool_logger.info(f"Recieved response from tool call {tool_call['id']}") 
            if not response.content:
                tool_logger.warning("Tool returned nothing! This might be an issue on the tool side.")
            return response       
        except Exception as e:
            tool_logger.error(f"Failed to use tool {tool_call['name']} with id {tool_call['id']}")
            artifact = {
                'error_type': type(e).__name__,
                'error_message': str(e),
                'tool_name': tool_call['name'],
                'tool_args': tool_call['args'],
                'timestamp': datetime.now().isoformat(),
            }

            import json
            error_content = f"""Failed to use tool: {str(e)}

Error details:
{json.dumps(artifact, indent=2)}"""

            return ToolMessage(
                content=error_content,
                tool_call_id=tool_call['id'],
                artifact=artifact,
            )
