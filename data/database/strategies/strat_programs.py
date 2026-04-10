"""Property extraction strategy for property programs."""

def run(file_name: str, file_content: str, chunk: str) -> list[str]:
    """
    Runs the property extraction strategy on processed chunk.

    Args:
	    file_name (str): Name of the file from which the chunk was collected.
	    file_content (str): Entire text extracted from file.
	    chunk (str): Chunk collected from file.

    Returns:
	    Extracted property.
	"""
    import re
    from collections import Counter

    counts = Counter()
    lc_text = file_content.lower()

    p_emba_x = r'emba\s+x\d*'
    p_iemba = r'iemba|international\s+emba|international\s+executive\s+mba'
    p_emba = r'emba|executive\s+mba'

    full_pattern = rf'\b({p_emba_x})\b|\b({p_iemba})\b|\b({p_emba})\b'

    for match in re.finditer(full_pattern, lc_text):
        if match.group(1):
            counts['emba_x'] += 1
        elif match.group(2):
            counts['iemba'] += 1
        elif match.group(3):
            counts['emba'] += 1

    if not counts:
        return []

    max_count = max(counts.values())

    programs = [
        prog for prog, count in counts.items()
        if count == max_count
    ]

    return programs