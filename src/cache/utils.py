import re 

def get_cache_key(key: str, language: str, session_id: str) -> str:
    normalized_key = re.sub(r'[^a-z0-9]', '', key.lower())
    return f"cache:{session_id}:{language}:{normalized_key}"
