from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from src.rag.models import ModelConfigurator as modconf
from src.rag.prompts import PromptConfigurator as promptconf

from src.utils.logging import get_logger

logger = get_logger('lang_detector')

class LanguageDetectionResult(BaseModel):
    language_code: str = Field(description="ISO language code (e.g., en, de, fa, ru) of the language in which the message is written")

class LanguageDetector:
    def __init__(self) -> None:
        self._model = modconf.get_language_detector_model()
        self._model = self._model.with_structured_output(LanguageDetectionResult)

    def detect_language(self, query: str) -> str:
        prompt = promptconf.get_language_detector_prompt(query)
        messages = [HumanMessage(prompt)]

        try:
            result = self._model.invoke(messages)
            return result.language_code
        except Exception as e:
            logger.error(f"Failed to detect language: {e}")
            return ""

