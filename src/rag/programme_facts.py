import re
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ProgrammeFacts:
    programme: str
    source_available: bool = False
    focus_points: list[str] = field(default_factory=list)
    fit_points: list[str] = field(default_factory=list)
    timing_points: list[str] = field(default_factory=list)
    document_points: list[str] = field(default_factory=list)
    raw_context: str = ""


class ProgrammeFactsProvider:
    """Extract lightweight programme facts from retrieved RAG context.

    This keeps volatile programme data in the scraped/imported knowledge base
    instead of hardcoding it in the conversation-routing layer.
    """

    _PROGRAM_FILTERS = {
        "emba": "emba",
        "iemba": "iemba",
        "emba_x": "emba x",
    }

    _QUERY_BY_LANGUAGE = {
        "de": (
            "Bewerbung Zulassung Voraussetzungen Studiengebühr Start Datum Dauer "
            "Bewerbungsfrist Unterlagen Dokumente CV Zeugnisse Führungserfahrung "
            "Berufserfahrung Sprache Module Präsenzwochen Wahlkurse Capstone"
        ),
        "en": (
            "application admissions requirements tuition start date duration deadline "
            "documents CV certificates transcripts leadership experience professional "
            "experience language modules campus weeks electives capstone"
        ),
    }

    _FOCUS_TERMS = (
        "focus",
        "ziel",
        "ziele",
        "fokus",
        "management",
        "leadership",
        "transformation",
        "innovation",
        "international",
        "dach",
    )
    _FIT_TERMS = (
        "requirement",
        "requirements",
        "admission",
        "admissions",
        "zulassung",
        "voraussetzung",
        "degree",
        "abschluss",
        "experience",
        "erfahrung",
        "leadership",
        "führung",
        "fuehrung",
        "english",
        "englisch",
        "german",
        "deutsch",
    )
    _TIMING_TERMS = (
        "tuition",
        "fee",
        "fees",
        "studiengebühr",
        "studiengebuehr",
        "chf",
        "start",
        "duration",
        "dauer",
        "months",
        "monate",
        "deadline",
        "bewerbungsfrist",
        "core course",
        "kernkurs",
        "elective",
        "wahlkurs",
        "campus week",
        "präsenzwoche",
        "praesenzwoche",
        "abroad",
        "auslandsmodul",
        "capstone",
    )
    _DOCUMENT_TERMS = (
        "document",
        "documents",
        "unterlagen",
        "dokument",
        "dokumente",
        "cv",
        "resume",
        "zeugnis",
        "zeugnisse",
        "certificate",
        "certificates",
        "transcript",
        "motivation",
        "motivations",
        "application file",
        "bewerbungsakte",
    )
    _NOISE_TERMS = (
        "vielen dank für ihr interesse",
        "vielen dank fuer ihr interesse",
        "senior recruitment",
        "admissions manager",
        "bei allgemeinen anfragen",
        "allgemeinen anfragen",
        "kontakt cyra",
        "kontakt kristin",
        "kontakt teyuna",
        "impact story",
        "alumnus",
        "alumni",
        "wir sprachen mit",
        "du warst teilnehmer",
        "für mich war die",
        "fuer mich war die",
        "unterlagen und werkzeuge",
        "jeder kurswoche",
        "lernerfahrungen",
        "diplomarbeit",
        "preis ausgezeichnet",
    )

    def __init__(self, retrieve_context: Callable[[str, str, str], str]) -> None:
        self._retrieve_context = retrieve_context
        self._cache: dict[tuple[str, str], ProgrammeFacts] = {}

    def get_facts(self, programme: str, language: str) -> ProgrammeFacts:
        normalized_programme = self._normalize_programme(programme)
        normalized_language = language if language in {"de", "en"} else "en"
        cache_key = (normalized_programme, normalized_language)
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = self._QUERY_BY_LANGUAGE[normalized_language]
        program_filter = self._PROGRAM_FILTERS.get(normalized_programme, normalized_programme)

        try:
            context = self._retrieve_context(query, program_filter, normalized_language) or ""
        except Exception:
            context = ""

        facts = self._extract_facts(normalized_programme, context)
        if facts.source_available:
            self._cache[cache_key] = facts
        return facts

    def _extract_facts(self, programme: str, context: str) -> ProgrammeFacts:
        sentences = self._split_sentences(context)
        return ProgrammeFacts(
            programme=programme,
            source_available=bool(sentences),
            focus_points=self._select_sentences(sentences, self._FOCUS_TERMS, limit=2),
            fit_points=self._select_sentences(sentences, self._FIT_TERMS, limit=3),
            timing_points=self._select_sentences(sentences, self._TIMING_TERMS, limit=4),
            document_points=self._select_sentences(sentences, self._DOCUMENT_TERMS, limit=3),
            raw_context=context,
        )

    @staticmethod
    def _normalize_programme(programme: str) -> str:
        normalized = (programme or "").lower().replace("-", "_").replace(" ", "_")
        if normalized in {"emba_x", "embax"}:
            return "emba_x"
        if normalized in {"iemba", "iemba_hsg", "international_emba"}:
            return "iemba"
        return "emba" if normalized in {"emba", "emba_hsg"} else normalized

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        raw_text = (text or "").strip()
        if not raw_text:
            return []

        raw_text = re.sub(r"#{1,6}\s*", "\n", raw_text)
        raw_text = re.sub(r"\|", "\n", raw_text)
        chunks = re.split(r"\n+|(?<=[.!?])\s+|(?:\s+•\s+)", raw_text)
        sentences = []
        for chunk in chunks:
            normalized = re.sub(r"\s+", " ", chunk).strip(" -•\t\n")
            normalized_lower = normalized.lower()
            has_compact_fact = bool(re.search(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b|chf\s*[\d']", normalized_lower))
            if len(normalized) < 20 and not has_compact_fact:
                continue
            if any(term in normalized_lower for term in ProgrammeFactsProvider._NOISE_TERMS):
                continue
            if len(normalized) > 320:
                normalized = normalized[:317].rstrip() + "..."
            sentences.append(normalized)
        return sentences

    @staticmethod
    def _select_sentences(sentences: list[str], terms: tuple[str, ...], limit: int) -> list[str]:
        selected = []
        seen = set()
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
