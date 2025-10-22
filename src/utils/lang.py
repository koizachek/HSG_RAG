from langdetect import detect 

def detect_language(text: str):
    """
    Detect the language of the given text.

    Args:
        text (str): The text to analyze.

    Returns:
        str: Detected language code ('de' or 'en').
    """
    return 'de' if detect(text) == 'de' else 'en'
    
