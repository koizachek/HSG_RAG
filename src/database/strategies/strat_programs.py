"""Property extraction strategy for programme classification."""


def run(file_name: str, file_content: str, chunk: str) -> list[str]:
    """
    Classify a chunk into one or more Executive MBA programme buckets.

    Scoring:
    - programme signal in the page address/path: +2.0
    - programme signal in the chunk: +1.0
    - programme signal in the whole document: +0.5 per occurrence

    The shared ``emba.unisg.ch`` host is not counted as an EMBA HSG signal;
    otherwise every shared admissions page would be biased toward ``emba``.
    """
    import re
    from collections import Counter
    from urllib.parse import urlparse

    programmes = ("emba", "iemba", "emba_x")
    scores = Counter({programme: 0.0 for programme in programmes})

    address_text = _address_text(file_name, urlparse, re)
    chunk_text = chunk or ""
    document_text = file_content or ""

    shared_requirements = _is_shared_emba_iemba_requirements(chunk_text)
    if shared_requirements and _is_embax_redirect_only(chunk_text):
        return ["emba", "iemba"]

    if shared_requirements:
        scores["emba"] += 1.0
        scores["iemba"] += 1.0

    for programme in programmes:
        if _contains_programme_signal(address_text, programme, re):
            scores[programme] += 2.0

        if _contains_programme_signal(chunk_text, programme, re):
            scores[programme] += 1.0

        scores[programme] += 0.5 * _count_programme_signals(document_text, programme, re)

    positive_scores = {
        programme: score
        for programme, score in scores.items()
        if score > 0
    }
    if not positive_scores:
        return []

    max_score = max(positive_scores.values())
    threshold = max(1.0, max_score - 0.5)

    return [
        programme
        for programme in programmes
        if positive_scores.get(programme, 0.0) >= threshold
    ]


def _address_text(file_name: str, urlparse, re) -> str:
    address = (file_name or "").lower()
    parsed = urlparse(address)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc
        path = parsed.path
        # emba.unisg.ch is the shared Executive MBA site, not the German EMBA
        # programme itself. Keep programme-specific hosts such as embax.ch.
        host_text = "" if host in {"emba.unisg.ch", "www.emba.unisg.ch"} else host
        return f"{host_text} {path}".replace("-", " ").replace("_", " ")

    # Local extracted filenames often start with the shared host prefix.
    address = re.sub(r"^emba[-_]unisg[-_]ch[-_]?", "", address)
    return address.replace("-", " ").replace("_", " ")


def _contains_programme_signal(text: str, programme: str, re) -> bool:
    return _count_programme_signals(text, programme, re) > 0


def _count_programme_signals(text: str, programme: str, re) -> int:
    text = text or ""
    patterns = {
        "emba_x": [
            r"\bemba\s*x\d*\b",
            r"\bembax\b",
            r"\bemba\s+eth\s+hsg\b",
            r"\bemba\s+eth\s+zurich\s*\+\s*university\s+of\s+st\.?gallen\b",
        ],
        "iemba": [
            r"\biemba(?:\s+hsg)?\b",
            r"\binternational\s+emba(?:\s+hsg)?\b",
            r"\binternational\s+executive\s+mba(?:\s+hsg)?\b",
        ],
        "emba": [
            r"(?<!international\s)\bemba\s+hsg\b",
            r"(?<!international\s)\bexecutive\s+mba\s+hsg\b(?!\s+programmes\b|\s+programs\b)",
            r"\bemba\s+\d{2}\b",
            r"\bgerman[-\s]speaking\s+programme\b",
            r"\bgerman[-\s]speaking\s+program\b",
        ],
    }
    return sum(
        len(re.findall(pattern, text, flags=re.IGNORECASE))
        for pattern in patterns.get(programme, [])
    )


def _is_shared_emba_iemba_requirements(text: str) -> bool:
    text_lower = (text or "").lower()
    return (
        "application requirements" in text_lower
        and "executive mba hsg programmes" in text_lower
        and "minimum 5 years" in text_lower
        and "minimum 3 years" in text_lower
    )


def _is_embax_redirect_only(text: str) -> bool:
    text_lower = (text or "").lower()
    return (
        "for emba x programme application requirements click" in text_lower
        or "for emba x program application requirements click" in text_lower
    )
