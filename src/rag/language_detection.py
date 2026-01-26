from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from src.rag.models import ModelConfigurator as modconf
from src.rag.prompts import PromptConfigurator as promptconf

from src.utils.logging import get_logger

logger = get_logger('lang_detector')

# Common short words for quick language detection (no LLM needed)
SHORT_WORDS_DE = {
    'ja', 'nein', 'danke', 'bitte', 'ok', 'gut', 'hallo', 'hi', 'hey',
    'genau', 'stimmt', 'klar', 'super', 'prima', 'toll', 'schön',
    'mehr', 'weniger', 'was', 'wie', 'wo', 'wann', 'warum', 'wer',
    'und', 'oder', 'aber', 'doch', 'noch', 'schon', 'jetzt', 'hier',
    'gerne', 'natürlich', 'sicher', 'vielleicht', 'also', 'ach', 'aha',
}
SHORT_WORDS_EN = {
    'yes', 'no', 'thanks', 'please', 'ok', 'okay', 'good', 'hello', 'hi', 'hey',
    'right', 'sure', 'great', 'nice', 'cool', 'fine', 'perfect',
    'more', 'less', 'what', 'how', 'where', 'when', 'why', 'who',
    'and', 'or', 'but', 'yet', 'now', 'here', 'there',
    'maybe', 'probably', 'definitely', 'certainly', 'alright',
}


class LanguageDetectionResult(BaseModel):
    language_code: str = Field(description="ISO language code (e.g., en, de, fa, ru) of the language in which the message is written")


class LanguageDetector:
    def __init__(self) -> None:
        self._model = modconf.get_language_detector_model()
        self._model = self._model.with_structured_output(LanguageDetectionResult)

    def _quick_detect_short_words(self, query: str) -> str | None:
        """Quick detection for short inputs using word dictionary. Returns None if not detected."""
        words = query.lower().strip().split()
        if len(words) > 3:
            return None

        # Check each word against dictionaries
        de_matches = sum(1 for w in words if w in SHORT_WORDS_DE)
        en_matches = sum(1 for w in words if w in SHORT_WORDS_EN)

        if de_matches > en_matches:
            logger.info(f"Quick detection: '{query}' -> German (dictionary match)")
            return 'de'
        elif en_matches > de_matches:
            logger.info(f"Quick detection: '{query}' -> English (dictionary match)")
            return 'en'

        return None

    def detect_language(self, query: str) -> str:
        # Try quick detection for short inputs first
        quick_result = self._quick_detect_short_words(query)
        if quick_result:
            return quick_result

        # Fall back to LLM for longer/ambiguous inputs
        prompt = promptconf.get_language_detector_prompt(query)
        messages = [HumanMessage(prompt)]

        try:
            result = self._model.invoke(messages)
            return result.language_code
        except Exception as e:
            logger.error(f"Failed to detect language: {e}")
            return ""

