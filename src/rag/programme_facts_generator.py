import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.database.weavservice import WeaviateService
from src.rag.programme_facts import DEFAULT_PROGRAMME_FACTS_PATH, ProgrammeFactsProvider
from src.utils.logging import get_logger

logger = get_logger("rag.programme_facts_generator")


PROGRAMMES = ("emba", "iemba", "emba_x")
LANGUAGES = ("de", "en")


def _retrieve_context_from_db(service: WeaviateService, query: str, program: str, language: str) -> str:
    program_filter = ProgrammeFactsProvider._PROGRAM_FILTERS.get(program, program)
    response, _elapsed = service.query(
        query=query,
        lang=language,
        property_filters={"programs": [program_filter]},
        limit=8,
    )
    return "\n\n".join(obj.properties.get("body", "") for obj in response.objects)


def _sentences_matching(sentences: list[str], *terms: str, limit: int = 4) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if sentence_lower in seen:
            continue
        if any(term in sentence_lower for term in terms):
            selected.append(sentence)
            seen.add(sentence_lower)
        if len(selected) >= limit:
            break
    return selected


def _extract_tuition(programme: str, raw_context: str, tuition_sentences: list[str]) -> str | None:
    normalized = re.sub(r"\s+", " ", raw_context)
    amount_pattern = r"CHF\s*\d{1,3}(?:['., ]\d{3})"
    label_patterns = {
        "emba": [
            r"\bEMBA\s*71\b",
            r"\bEMBA\s+HSG\b",
            r"\bExecutive\s+MBA\s+HSG\b",
        ],
        "iemba": [
            r"\bIEMBA\s*14\b",
            r"\bIEMBA\s+HSG\b",
            r"\bInternational\s+EMBA\s+HSG\b",
        ],
        "emba_x": [
            r"\bemba\s*X\b",
            r"\bEMBA\s+ETH\b",
            r"\bEMBA\s+ETH\s+Zurich\b",
        ],
    }
    stop_labels = {
        "emba": r"\b(?:IEMBA|International\s+EMBA|emba\s*X|EMBA\s+ETH)\b",
        "iemba": r"\b(?:EMBA\s*71|Executive\s+MBA\s+HSG|emba\s*X|EMBA\s+ETH)\b",
        "emba_x": r"\b(?:IEMBA|International\s+EMBA|EMBA\s*71|Executive\s+MBA\s+HSG)\b",
    }

    for label_pattern in label_patterns.get(programme, []):
        for label_match in re.finditer(label_pattern, normalized, flags=re.IGNORECASE):
            window = normalized[label_match.end(): label_match.end() + 700]
            stop_match = re.search(stop_labels[programme], window, flags=re.IGNORECASE)
            if stop_match:
                window = window[:stop_match.start()]
            amounts = re.findall(amount_pattern, window, flags=re.IGNORECASE)
            if amounts:
                return amounts[-1]

    for sentence in tuition_sentences:
        sentence_lower = sentence.lower()
        if programme == "emba" and ("iemba" in sentence_lower or "international emba" in sentence_lower or "emba x" in sentence_lower):
            continue
        if programme == "iemba" and not ("iemba" in sentence_lower or "international emba" in sentence_lower):
            continue
        if programme == "emba_x" and not ("emba x" in sentence_lower or "emba eth" in sentence_lower):
            continue
        amounts = re.findall(amount_pattern, sentence, flags=re.IGNORECASE)
        if amounts:
            return amounts[-1]
    return None


def _extract_structured_record(programme: str, raw_context: str) -> dict[str, Any]:
    sentences = ProgrammeFactsProvider._split_sentences(raw_context)
    tuition_sentences = _sentences_matching(
        sentences,
        "chf",
        "tuition",
        "studiengebühr",
        "studiengebuehr",
        "fee",
        limit=5,
    )
    tuition = _extract_tuition(programme, raw_context, tuition_sentences)

    record: dict[str, Any] = {
        "tuition": tuition,
        "tuition_context": tuition_sentences,
        "deadlines": _sentences_matching(sentences, "deadline", "bewerbungsfrist", "application deadline", limit=5),
        "start_dates": _sentences_matching(sentences, "start", "beginn", "program-start", "programm-start", limit=4),
        "duration": _sentences_matching(sentences, "duration", "dauer", "months", "monate", limit=3),
        "language": _sentences_matching(sentences, "language", "sprache", "english", "englisch", "german", "deutsch", limit=3),
        "format": _sentences_matching(sentences, "format", "modular", "part-time", "berufsbegleitend", "online", limit=4),
        "locations": _sentences_matching(sentences, "location", "standort", "campus", "st.gallen", "zürich", "zurich", limit=4),
        "admissions": _sentences_matching(sentences, "admission", "zulassung", "requirement", "voraussetzung", limit=5),
        "documents": _sentences_matching(sentences, "document", "unterlagen", "cv", "transcript", "zeugnis", limit=4),
        "focus": _sentences_matching(sentences, "focus", "fokus", "leadership", "management", "transformation", limit=4),
    }
    return {key: value for key, value in record.items() if value}


def generate_programme_facts_json(
    output_path: Path | str = DEFAULT_PROGRAMME_FACTS_PATH,
    service: WeaviateService | None = None,
) -> Path:
    """Generate structured programme facts from the current Weaviate database."""

    service = service or WeaviateService()
    output = Path(output_path)
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "weaviate",
        "programmes": {},
    }

    provider = ProgrammeFactsProvider(lambda query, program, language: _retrieve_context_from_db(service, query, program, language))
    for programme in PROGRAMMES:
        payload["programmes"][programme] = {}
        for language in LANGUAGES:
            if programme == "emba_x" and language == "de":
                continue
            facts = provider.get_facts(programme, language)
            if not facts.raw_context:
                logger.warning("No programme facts context found for %s/%s", programme, language)
                continue
            payload["programmes"][programme][language] = _extract_structured_record(programme, facts.raw_context)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote structured programme facts JSON to %s", output)
    return output


if __name__ == "__main__":
    generate_programme_facts_json()
