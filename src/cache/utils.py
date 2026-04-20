import re 

def get_cache_key(key: str, language: str) -> str:
    normalized_key = re.sub(r'[^a-z0-9]', '', key.lower())
    return f"cache:{language}:{normalized_key}"
