from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException
from src.utils.logging import get_logger

from src.config import config

logger = get_logger('lang_utils')
DetectorFactory.seed = 0


def detect_language_profile(text: str) -> tuple[str, float] | None:
    """
    Return langdetect's top language candidate and probability.
    """
    try:
        found_langs = detect_langs(text)
    except LangDetectException:
        return None

    if not found_langs:
        return None

    top_lang = found_langs[0]
    logger.debug(
        'Found following languages in the text: '
        + ', '.join(f'{lang.lang}-{lang.prob:1.2f}' for lang in found_langs)
    )
    return top_lang.lang, top_lang.prob


def detect_language(text: str):
    """
    Detects if the provided text is written in German or in some other language. 
    In case of ambiguous input returns 'en'.

    Args:
        text (str): The text to analyze.

    Returns:
        str: 'de' if the detection certanty is more than 0.6, else 'en'.
    """
    profile = detect_language_profile(text)
    if not profile:
        return 'en'

    top_lang, probability = profile
    return 'de' if top_lang == 'de' and probability >= config.processing.LANG_AMBIGUITY_THRESHOLD else 'en'
    

def get_language_name(code: str):
    return {
        'en': "British English",
        'de': "German",
    }.get(code, 'British English')
