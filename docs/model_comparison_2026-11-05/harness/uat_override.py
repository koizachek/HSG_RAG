"""Per-run model override for a UAT comparison; lives outside the repo."""
import os
import config
import langchain_openai

model, effort = os.environ["CMP_MODEL"], os.environ.get("CMP_EFFORT", "")
config.MAIN_AGENT_MODEL = ("open_router:openai", model)
config.LOGS_PATH = os.environ["CMP_LOGS"]
os.makedirs(config.LOGS_PATH, exist_ok=True)

_Orig = langchain_openai.ChatOpenAI
def _patched(*args, **kwargs):
    if kwargs.get("model") == model and effort:
        kwargs["extra_body"] = {"reasoning": {"effort": effort}}
    return _Orig(*args, **kwargs)
langchain_openai.ChatOpenAI = _patched
config.OPEN_ROUTER_REASONING_EFFORT = {"main": effort} if effort else {}
