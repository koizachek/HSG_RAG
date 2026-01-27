from langdetect import DetectorFactory, detect_langs
from src.utils.logging import get_logger

from config import LANG_AMBIGUITY_THRESHOLD

logger = get_logger('lang_utils')
DetectorFactory.seed = 0

def detect_language(text: str):
    """
    Detects if the provided text is written in German or in some other language. 
    In case of ambiguous input returns 'en'.

    Args:
        text (str): The text to analyze.

    Returns:
        str: 'de' if the detection certanty is more than 0.6, else 'en'.
    """
    found_langs = detect_langs(text)
    top_lang = found_langs[0]
    logger.info(f'Found following languages in the text: {", ".join(f"{lang.lang}-{lang.prob:1.2f}" for lang in found_langs)}')
    return 'de' if top_lang.lang == 'de' and top_lang.prob >= LANG_AMBIGUITY_THRESHOLD else 'en'
    

def get_language_name(code: str):
    return {
        'en': "British English",
        'de': "German",
    }.get(code, 'British English')
