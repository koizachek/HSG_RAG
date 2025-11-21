from langdetect import detect 

def detect_language(text: str):
    """
    Detect the language of the given text.

    Args:
        text (str): The text to analyze.

    Returns:
        str: Detected language code.
    """
    return 'de' if detect(text) == 'de' else 'en'
    

def get_language_name(code: str):
    return {
        'en': "English",
        'de': "German",
    }.get(code, 'English')
