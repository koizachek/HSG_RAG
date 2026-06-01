import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable


@dataclass
class ProgrammeFacts:
    programme: str
    source_available: bool = False
    focus_points: list[str] = field(default_factory=list)
    fit_points: list[str] = field(default_factory=list)
    timing_points: list[str] = field(default_factory=list)
    document_points: list[str] = field(default_factory=list)
    raw_context: str = ""
    structured: dict[str, Any] = field(default_factory=dict)


DEFAULT_PROGRAMME_FACTS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "programme_facts" / "programme_facts.json"
)


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
        "online-bewerbung",
        "online application",
        "online-assessment",
        "online assessment",
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
        "kontakt admissions",
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
        "ich bin mir ganz sicher",
        "beruflichen fortschritt",
        "tools, dem netzwerk",
        "hsg mitnehmen",
    )
    _RAW_DUMP_TERMS = (
        "with this programme, two top swiss institutions join forces",
        "innovative executive education curriculum",
        "get in touch - share your cv with us",
        "share your cv with us and see if your profile",
        "incentive award",
        "tuition incentive",
        "tuition incentives",
        "merit-based tuition",
        "these are not guaranteed",
        "download brochure",
        "request brochure",
        "first application deadline",
        "final application deadline",
    )
    _MAX_PARALLEL_RETRIEVALS = 3

    def __init__(self, retrieve_context: Callable[[str, str, str], str]) -> None:
        self._retrieve_context = retrieve_context
        self._cache: dict[tuple[str, str], ProgrammeFacts] = {}
        self._cache_lock = Lock()

    def get_facts(self, programme: str, language: str) -> ProgrammeFacts:
        normalized_programme = self._normalize_programme(programme)
        normalized_language = language if language in {"de", "en"} else "en"
        cache_key = (normalized_programme, normalized_language)
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        facts = self._retrieve_facts(normalized_programme, normalized_language)
        if facts.source_available:
            with self._cache_lock:
                self._cache[cache_key] = facts
        return facts

    def get_facts_many(self, programmes: list[str], language: str) -> dict[str, ProgrammeFacts]:
        normalized_language = language if language in {"de", "en"} else "en"
        normalized_programmes = list(dict.fromkeys(
            self._normalize_programme(programme)
            for programme in programmes
        ))
        facts_by_programme: dict[str, ProgrammeFacts] = {}
        missing_programmes: list[str] = []

        with self._cache_lock:
            for programme in normalized_programmes:
                cache_key = (programme, normalized_language)
                if cache_key in self._cache:
                    facts_by_programme[programme] = self._cache[cache_key]
                else:
                    missing_programmes.append(programme)

        if not missing_programmes:
            return facts_by_programme

        result_lock = Lock()

        def retrieve_missing(programme: str) -> None:
            try:
                facts = self._retrieve_facts(programme, normalized_language)
            except Exception:
                facts = ProgrammeFacts(programme=programme)

            with result_lock:
                facts_by_programme[programme] = facts
            if facts.source_available:
                with self._cache_lock:
                    self._cache[(programme, normalized_language)] = facts

        max_workers = min(self._MAX_PARALLEL_RETRIEVALS, len(missing_programmes))
        for batch_start in range(0, len(missing_programmes), max_workers):
            threads = [
                Thread(target=retrieve_missing, args=(programme,))
                for programme in missing_programmes[batch_start:batch_start + max_workers]
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        return {
            programme: facts_by_programme.get(programme, ProgrammeFacts(programme=programme))
            for programme in normalized_programmes
        }

    def _retrieve_facts(self, normalized_programme: str, normalized_language: str) -> ProgrammeFacts:
        query = self._QUERY_BY_LANGUAGE[normalized_language]
        program_filter = self._PROGRAM_FILTERS.get(normalized_programme, normalized_programme)

        try:
            context = self._retrieve_context(query, program_filter, normalized_language) or ""
        except Exception:
            context = ""

        return self._extract_facts(normalized_programme, context)

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
            if any(term in sentence_lower for term in ProgrammeFactsProvider._RAW_DUMP_TERMS):
                continue
            if any(term in sentence_lower for term in terms):
                selected.append(sentence)
                seen.add(sentence_lower)
            if len(selected) >= limit:
                break
        return selected


class JsonProgrammeFactsProvider(ProgrammeFactsProvider):
    """Serve structured facts generated from the database, with RAG fallback.

    This is an optional cache/index layer derived from the scraped Weaviate
    corpus. It must not be maintained as an independent source of programme
    truth or contain hand-written business rules.
    """

    def __init__(
        self,
        retrieve_context: Callable[[str, str, str], str],
        facts_path: Path | str = DEFAULT_PROGRAMME_FACTS_PATH,
    ) -> None:
        super().__init__(retrieve_context)
        self._facts_path = Path(facts_path)
        self._json_payload: dict[str, Any] | None = None

    def get_facts(self, programme: str, language: str) -> ProgrammeFacts:
        normalized_programme = self._normalize_programme(programme)
        normalized_language = language if language in {"de", "en"} else "en"
        record = self._json_record(normalized_programme, normalized_language)
        if record:
            return self._facts_from_json_record(normalized_programme, record)
        return super().get_facts(normalized_programme, normalized_language)

    def get_facts_many(self, programmes: list[str], language: str) -> dict[str, ProgrammeFacts]:
        normalized_language = language if language in {"de", "en"} else "en"
        return {
            self._normalize_programme(programme): self.get_facts(programme, normalized_language)
            for programme in programmes
        }

    def _load_json_payload(self) -> dict[str, Any]:
        if self._json_payload is not None:
            return self._json_payload
        if not self._facts_path.exists():
            self._try_generate_json_payload()
        if not self._facts_path.exists():
            self._json_payload = {}
            return self._json_payload
        try:
            self._json_payload = json.loads(self._facts_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._json_payload = {}
        return self._json_payload

    def _try_generate_json_payload(self) -> None:
        try:
            from src.rag.programme_facts_generator import generate_programme_facts_json

            generate_programme_facts_json(self._facts_path)
        except Exception as exc:
            chain_logger = None
            try:
                from src.utils.logging import get_logger

                chain_logger = get_logger("programme_facts")
            except Exception:
                chain_logger = None
            if chain_logger is not None:
                chain_logger.warning(
                    "Could not generate structured programme facts JSON at %s: %s",
                    self._facts_path,
                    exc,
                )

    def _json_record(self, programme: str, language: str) -> dict[str, Any]:
        payload = self._load_json_payload()
        programmes = payload.get("programmes", {}) if isinstance(payload, dict) else {}
        programme_record = programmes.get(programme, {}) if isinstance(programmes, dict) else {}
        language_record = programme_record.get(language) or programme_record.get("en") or {}
        return language_record if isinstance(language_record, dict) else {}

    @staticmethod
    def _facts_from_json_record(programme: str, record: dict[str, Any]) -> ProgrammeFacts:
        def list_value(*keys: str) -> list[str]:
            values: list[str] = []
            for key in keys:
                value = record.get(key)
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
                elif isinstance(value, list):
                    values.extend(str(item).strip() for item in value if str(item).strip())
            return values

        timing_points = list_value(
            "tuition",
            "deadlines",
            "start_dates",
            "duration",
            "format",
            "locations",
            "language",
        )
        fit_points = list_value("admissions", "requirements", "target_group")
        focus_points = list_value("focus", "value_proposition")
        document_points = list_value("documents")

        raw_context = "\n".join(focus_points + fit_points + timing_points + document_points)
        return ProgrammeFacts(
            programme=programme,
            source_available=bool(raw_context),
            focus_points=focus_points,
            fit_points=fit_points,
            timing_points=timing_points,
            document_points=document_points,
            raw_context=raw_context,
            structured=record,
        )
