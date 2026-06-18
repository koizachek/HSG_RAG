"""
Regenerate data/database/programme_facts.json from the official programme websites.

Offline fact-extraction step (multi-agent offline, single-agent online):
this script runs OUTSIDE the chat request path — manually, via cron, or as a
post-scrape pipeline step. It fetches the official sources, lets an LLM
extract the volatile core facts into a strict schema, diffs against the
current facts file, and alerts via the notification center when facts changed.

Usage:
    python -m src.pipeline.update_programme_facts            # update + diff alert
    python -m src.pipeline.update_programme_facts --dry-run  # show diff only
"""
import argparse
import html
import json
import os
import re
import sys
import unicodedata
from datetime import date
from tempfile import NamedTemporaryFile

import requests
from pydantic import BaseModel, Field

from src.config import config
from src.utils.logging import get_logger

logger = get_logger('update_programme_facts')

FACTS_PATH = os.path.join(config.paths.DATA, 'database', 'programme_facts.json')

# Pages and data-plan PDFs that contain the volatile core facts.
FACT_SOURCES = {
    'overview':  'https://emba.unisg.ch/',
    'deadlines': 'https://emba.unisg.ch/bewerbung/fristen',
    'emba':      'https://emba.unisg.ch/programm/emba',
    'iemba':     'https://emba.unisg.ch/programm/iemba',
    'iemba_es':  'https://es.unisg.ch/en/executive-programme/international-executive-mba-hsg/',
    'emba_x':    'https://embax.ch/',
    'emba_plan': 'https://emba.unisg.ch/wp-content/uploads/2026/05/Neuer-Dataplan-EMBA71-mitRatenplan.pdf',
    'iemba_plan': 'https://emba.unisg.ch/wp-content/uploads/2026/05/IEMBA-14-info-sheet-with-payment-plan-6.pdf',
}

REQUEST_TIMEOUT = 30
REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.9,*/*;q=0.8',
    'Accept-Language': 'de-CH,de;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Cache-Control': 'no-cache',
}
FALLBACK_REQUEST_HEADERS = {
    **REQUEST_HEADERS,
    'Referer': 'https://emba.unisg.ch/',
}


# ----------------------------- Extraction schema -----------------------------

class DeadlineFee(BaseModel):
    deadline: str = Field(description="Application deadline as ISO date YYYY-MM-DD")
    fee: int = Field(description="Tuition fee in CHF as plain integer, e.g. 77500")


class BilingualText(BaseModel):
    de: str = Field(description="German wording")
    en: str = Field(description="English wording")


class ProgrammeFactsSchema(BaseModel):
    official_name: str
    current_cohort: str = Field(description="e.g. 'EMBA 71', 'IEMBA 14', 'emba X6'")
    language: BilingualText = Field(description="Programme teaching language")
    programme_start: str = Field(description="ISO date YYYY-MM-DD of the next cohort start")
    duration: BilingualText
    ects_credits: int = Field(default=0, description="ECTS credits as plain integer, e.g. 75; 0 if missing")
    structure: BilingualText = Field(description="Courses, campus weeks, projects")
    locations: BilingualText
    first_deadline: DeadlineFee
    final_deadline: DeadlineFee
    advisor_name: str
    advisor_email: str
    advisor_phone: str


class AllProgrammesSchema(BaseModel):
    emba: ProgrammeFactsSchema
    iemba: ProgrammeFactsSchema
    emba_x: ProgrammeFactsSchema


class FactComparisonDecision(BaseModel):
    materially_changed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    fact_value: str
    preserve_existing: bool


EXTRACTION_PROMPT = """You are a fact extraction system. Below is the text content of the
official HSG Executive MBA websites. Extract the CURRENT facts for the three
programmes EMBA HSG (German), IEMBA HSG (International, English) and
emba X (ETH Zurich & University of St.Gallen joint degree, English).

Rules:
- Use ONLY facts that literally appear in the provided page content.
- Never guess or fill gaps from prior knowledge. If a value is genuinely
  missing from the pages, use an empty string.
- Fees are CHF integers without separators (CHF 77'500 -> 77500).
- ECTS credits are plain integers (75 ECTS -> 75). If missing, use 0.
- Dates in ISO format (14. September 2026 -> 2026-09-14).
- Never mix values between programmes. The deadlines page contains one row
  per programme - keep them strictly separated.
- Currently stored facts are provided for stability and comparison only. Do not
  use them to fill missing page content, but if the page expresses the same
  fact with different punctuation, word order, translation-equivalent wording,
  or minor synonyms, prefer the existing stable wording.

CURRENTLY STORED FACTS:
{existing_facts_context}

PAGE CONTENT:
{page_content}"""


FACT_COMPARISON_PROMPT = """You compare one stored programme fact with a newly
observed fact extracted from official page content.

Rules:
- Return materially_changed=false when the page expresses the same factual
  content, even if wording, punctuation, formatting, translation, or synonyms
  differ.
- Return materially_changed=true only for real factual differences: fees,
  deadlines, start dates, numbers of courses/modules/electives, campus weeks,
  admissions requirements, duration, degree/certificate/title, language,
  location, format, or a component being added or removed.
- Be conservative. If the difference is stylistic or ambiguous, preserve the
  existing value and set preserve_existing=true.
- If the page contains the same information expressed differently, keep the
  existing stored fact as fact_value.

Fact key: {fact_key}
Language: {language}
Source: {source_info}
Currently stored value:
{existing_value}

Newly observed/extracted value:
{observed_value}

Relevant page snippet:
{page_content}"""


# --------------------------------- Fetching ----------------------------------

def extract_pdf_text(content: bytes, url: str) -> str:
    """Extract text from a PDF response using available local parsers."""
    if not content.lstrip().startswith(b'%PDF'):
        logger.warning(f"PDF URL did not return PDF bytes: {url}")
        try:
            text = content.decode('utf-8', errors='ignore')
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, 'html.parser')
            for tag in soup(['script', 'style', 'noscript']):
                tag.decompose()
            return soup.get_text(separator='\n', strip=True)
        except Exception:
            return content.decode('utf-8', errors='ignore')

    suffix = os.path.splitext(url)[1] or '.pdf'
    with NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        try:
            from docling.document_converter import DocumentConverter
            result = DocumentConverter().convert(tmp_path)
            return result.document.export_to_markdown()
        except Exception as docling_error:
            logger.warning(f"Docling could not parse PDF {url}; trying fallback parser: {docling_error}")

        try:
            from pypdf import PdfReader
            reader = PdfReader(tmp_path)
            return "\n\n".join(page.extract_text() or '' for page in reader.pages).strip()
        except Exception as pypdf_error:
            logger.warning(f"Fallback PDF parser could not parse {url}: {pypdf_error}")
            raise
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _extract_fact_html_snippets(text: str) -> str:
    """Keep structured fact blocks before converting the page to visible text."""
    matches = re.findall(
        r'<div[^>]*class=["\'][^"\']*\blocations\b[^"\']*["\'][^>]*>.*?</div>',
        text or '',
        flags=re.IGNORECASE | re.DOTALL,
    )
    return "\n".join(matches)


def fetch_sources() -> dict[str, str]:
    """Fetch all fact source pages. Raises when a page cannot be fetched."""
    pages = {}
    session = requests.Session()
    for key, url in FACT_SOURCES.items():
        logger.info(f"Fetching {url}")
        resp = session.get(url, timeout=REQUEST_TIMEOUT, headers=REQUEST_HEADERS)
        if resp.status_code == 415:
            logger.warning(f"Retrying {url} after HTTP 415 with fallback headers")
            resp = session.get(url, timeout=REQUEST_TIMEOUT, headers=FALLBACK_REQUEST_HEADERS)
        resp.raise_for_status()
        content_type = resp.headers.get('Content-Type', '').lower()
        if url.lower().endswith('.pdf') or 'application/pdf' in content_type:
            try:
                pages[key] = extract_pdf_text(resp.content, url)
            except Exception as exc:
                logger.warning(f"Skipping unreadable PDF source {url}: {exc}")
                pages[key] = ''
            continue
        # Lightweight HTML -> text. The scraping pipeline has richer
        # processors; for fact extraction visible text is sufficient.
        fact_html = _extract_fact_html_snippets(resp.text)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(['script', 'style', 'noscript']):
                tag.decompose()
            visible_text = soup.get_text(separator='\n', strip=True)
            pages[key] = "\n\n".join(part for part in (fact_html, visible_text) if part)
        except ImportError:
            pages[key] = resp.text
    return pages


# -------------------------------- Extraction ---------------------------------

def _existing_facts_context(existing_facts: dict | None) -> str:
    if not existing_facts:
        return "No currently stored facts were provided."
    return json.dumps(
        existing_facts.get('programmes', existing_facts),
        indent=2,
        ensure_ascii=False,
    )[:20000]


def extract_facts(pages: dict[str, str], existing_facts: dict | None = None) -> AllProgrammesSchema:
    """LLM-based structured extraction over the fetched pages."""
    from src.rag.models import ModelConfigurator
    model = ModelConfigurator.get_main_agent_model().with_structured_output(
        AllProgrammesSchema
    )
    page_content = "\n\n".join(
        f"===== SOURCE: {FACT_SOURCES[key]} =====\n{text[:20000]}"
        for key, text in pages.items()
    )
    return model.invoke(EXTRACTION_PROMPT.format(
        existing_facts_context=_existing_facts_context(existing_facts),
        page_content=page_content,
    ))


def _extract_ects_credits(text: str) -> int:
    """Deterministically extract ECTS credits from nearby label/value text."""
    patterns = [
        r'ECTS[-\s]*(?:Punkte|Credits?)\s*[:\n\r\s]+(\d{1,3})\b',
        r'(\d{1,3})\s*(?:ECTS|Credits?)\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def apply_deterministic_fallbacks(extracted: AllProgrammesSchema, pages: dict[str, str]) -> AllProgrammesSchema:
    """Fill simple numeric facts that the LLM occasionally misses."""
    fallback_sources = {
        'emba': ['emba_plan', 'emba'],
        'iemba': ['iemba_es', 'iemba_plan', 'iemba'],
        'emba_x': ['emba_x'],
    }
    for programme_key, source_keys in fallback_sources.items():
        programme = getattr(extracted, programme_key)
        if programme.ects_credits:
            continue
        for source_key in source_keys:
            ects = _extract_ects_credits(pages.get(source_key, ''))
            if ects:
                programme.ects_credits = ects
                break
    return extracted


LOCATION_TRANSLATIONS = {
    'Belgien': 'Belgium',
    'Belgium': 'Belgium',
    'Beijing': 'Beijing',
    'China': 'China',
    'Costa Rica': 'Costa Rica',
    'Italien': 'Italy',
    'Italy': 'Italy',
    'Japan': 'Japan',
    'Peking': 'Beijing',
    'Schweiz': 'Switzerland',
    'Switzerland': 'Switzerland',
    'South Africa': 'South Africa',
    'Spanien': 'Spain',
    'Spain': 'Spain',
    'Südafrika': 'South Africa',
    'Tokyo': 'Tokyo',
    'Tokio': 'Tokyo',
    'USA': 'USA',
}

LOCATION_COUNTRIES_DE = set(LOCATION_TRANSLATIONS)
LOCATION_ELECTIVE_MARKERS = {'wahlkurs', 'elective course', 'elective'}
LOCATION_SECTION_STARTS = {'orte', 'locations'}
LOCATION_SECTION_ENDS = {
    'courses',
    'course structure',
    'duration',
    'fees',
    'programme structure',
    'start',
    'total',
    'kurse',
    'dauer',
    'gebühr',
    'programmstruktur',
    'start',
}


def _clean_html_fragment(value: str) -> str:
    value = re.sub(r'<[^>]+>', '', value)
    value = html.unescape(value)
    return re.sub(r'\s+', ' ', value).strip()


def _canonicalize_location_de(value: str) -> str:
    value = re.sub(r'\s+', ' ', value).strip()
    parts = [part.strip() for part in value.split(',')]
    if len(parts) == 2 and parts[1] in LOCATION_COUNTRIES_DE:
        return f"{parts[1]} ({parts[0]})"
    return value


def _translate_location_name(value: str) -> str:
    match = re.fullmatch(r'(.+?) \((.+)\)', value)
    if match:
        country_de, place_de = match.groups()
        country_en = LOCATION_TRANSLATIONS.get(country_de, country_de)
        place_en = LOCATION_TRANSLATIONS.get(place_de, place_de)
        return f"{country_en} ({place_en})"
    return LOCATION_TRANSLATIONS.get(value, value)


def _locations_from_items(items: list[tuple[str, bool]]) -> BilingualText | None:
    de_locations = []
    en_locations = []
    for location_de, is_elective in items:
        location_de = _canonicalize_location_de(location_de)
        if not location_de:
            continue

        location_en = _translate_location_name(location_de)
        if is_elective:
            location_de = f"{location_de} (Wahlkurs)"
            location_en = f"{location_en} (elective)"
        de_locations.append(location_de)
        en_locations.append(location_en)

    if not de_locations:
        return None

    return BilingualText(de=', '.join(de_locations), en=', '.join(en_locations))


def _extract_locations_from_html(text: str) -> BilingualText | None:
    match = re.search(
        r'<div[^>]*class=["\'][^"\']*\blocations\b[^"\']*["\'][^>]*>\s*'
        r'<small>\s*Orte\s*</small>\s*<ul[^>]*>(.*?)</ul>',
        text or '',
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None

    items = []
    for item_html in re.findall(r'<li>(.*?)</li>', match.group(1), flags=re.IGNORECASE | re.DOTALL):
        is_elective = re.search(r'<small[^>]*>\s*Wahlkurs\s*</small>', item_html, flags=re.IGNORECASE)
        location_de = _clean_html_fragment(
            re.sub(r'<small[^>]*>.*?</small>', '', item_html, flags=re.IGNORECASE | re.DOTALL)
        )
        if location_de:
            items.append((location_de, bool(is_elective)))
    return _locations_from_items(items)


def _extract_locations_from_text(text: str) -> BilingualText | None:
    lines = [
        _clean_html_fragment(line)
        for line in (text or '').splitlines()
        if _clean_html_fragment(line)
    ]
    start_index = None
    for index, line in enumerate(lines):
        if _canonical_text(line) in LOCATION_SECTION_STARTS:
            start_index = index + 1
            break
    if start_index is None:
        return None

    items = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        canonical_line = _canonical_text(line)
        if canonical_line in LOCATION_SECTION_ENDS:
            break
        if canonical_line in LOCATION_ELECTIVE_MARKERS:
            index += 1
            continue

        next_line = lines[index + 1] if index + 1 < len(lines) else ''
        is_elective = _canonical_text(next_line) in LOCATION_ELECTIVE_MARKERS
        items.append((line, is_elective))
        index += 2 if is_elective else 1

    return _locations_from_items(items)


def _extract_locations_from_programme_page(text: str) -> BilingualText | None:
    """Deterministically parse the official programme-page locations block."""
    return _extract_locations_from_html(text) or _extract_locations_from_text(text)


def apply_deterministic_source_facts(extracted: AllProgrammesSchema, pages: dict[str, str]) -> AllProgrammesSchema:
    """Override LLM prose where the official page exposes a structured fact block."""
    source_keys_by_programme = {
        'emba': ['emba'],
        'iemba': ['iemba', 'iemba_es'],
    }
    for programme_key, source_keys in source_keys_by_programme.items():
        for source_key in source_keys:
            locations = _extract_locations_from_programme_page(pages.get(source_key, ''))
            if locations:
                getattr(extracted, programme_key).locations = locations
                break
    return extracted


def to_facts_document(extracted: AllProgrammesSchema) -> dict:
    """Convert the extraction schema into the programme_facts.json layout."""
    def programme(p: ProgrammeFactsSchema, source_urls: list[str]) -> dict:
        return {
            'official_name': p.official_name,
            'current_cohort': p.current_cohort,
            'language': p.language.model_dump(),
            'programme_start': p.programme_start,
            'duration': p.duration.model_dump(),
            'ects_credits': p.ects_credits,
            'structure': p.structure.model_dump(),
            'locations': p.locations.model_dump(),
            'tuition_chf': {
                'first_deadline': p.first_deadline.model_dump(),
                'final_deadline': p.final_deadline.model_dump(),
                'note': {
                    'de': 'Fristabhängige Studiengebühr: frühere Bewerbung = reduzierte Gebühr',
                    'en': 'Deadline-based tuition: earlier application = reduced fee',
                },
            },
            'advisor': {
                'name': p.advisor_name,
                'email': p.advisor_email,
                'phone': p.advisor_phone,
            },
            'source_urls': source_urls,
        }

    return {
        'generated_at': date.today().isoformat(),
        'generator': 'src/pipeline/update_programme_facts.py',
        'sources': list(FACT_SOURCES.values()),
        'programmes': {
            'emba': programme(extracted.emba, [FACT_SOURCES['emba'], FACT_SOURCES['deadlines'], FACT_SOURCES['emba_plan']]),
            'iemba': programme(extracted.iemba, [FACT_SOURCES['iemba'], FACT_SOURCES['iemba_es'], FACT_SOURCES['deadlines'], FACT_SOURCES['iemba_plan']]),
            'emba_x': programme(extracted.emba_x, [FACT_SOURCES['emba_x'], FACT_SOURCES['deadlines']]),
        },
    }


# ----------------------------------- Diff ------------------------------------

DESCRIPTIVE_FACT_SUFFIXES = (
    'duration.de',
    'duration.en',
    'structure.de',
    'structure.en',
)
LOCATION_FACT_SUFFIXES = (
    'locations.de',
    'locations.en',
)

FACT_COMPARISON_STOP_WORDS = {
    'a',
    'am',
    'and',
    'as',
    'at',
    'auf',
    'bis',
    'by',
    'das',
    'der',
    'die',
    'en',
    'for',
    'im',
    'in',
    'max',
    'maximum',
    'mit',
    'of',
    'on',
    'the',
    'to',
    'up',
    'und',
    'with',
}

FACT_SYNONYM_PHRASES = (
    (r'\bpersonal\s+development\s+program(?:me)?\b', 'personal development'),
    (r'\bpersonliche\s+entwicklung\b', 'personal development'),
    (r'\bpersoenliche\s+entwicklung\b', 'personal development'),
    (r'\bcapstone\s+projekt\b', 'capstone project'),
    (r'\bselbststudium\b', 'self study'),
    (r'\bself\s*study\b', 'self study'),
    (r'\bpflichtkurse?n?\b', 'core courses'),
    (r'\bwahlkurse?n?\b', 'electives'),
    (r'\bessential\s+kurse?n?\b', 'essential courses'),
    (r'\bwochen\s+am\s+campus\b', 'weeks on campus'),
    (r'\bwochen\s+im\s+ausland\b', 'weeks abroad'),
    (r'\bprogramm\b', 'program'),
    (r'\bprogramme\b', 'program'),
)

STRUCTURE_COMPONENT_PATTERNS = {
    'core_courses': r'\bcore\s+courses?\b',
    'electives': r'\belectives?\b',
    'campus_weeks': r'\bweeks?\s+on\s+campus\b',
    'abroad_weeks': r'\bweeks?\s+abroad\b',
    'capstone': r'\bcapstone\s+project\b',
    'self_study': r'\bself\s+study\b',
    'personal_development': r'\bpersonal\s+development\b',
    'thesis': r'\b(?:thesis|diplomarbeit)\b',
    'impact_projects': r'\bimpact\s+projects?\b',
    'online': r'\bonline\b',
    'essential_courses': r'\bessential\s+courses?\b',
}


def _flat_facts(d: dict, prefix: str = '') -> dict:
    items = {}
    for key, value in (d or {}).items():
        flat_key = f"{prefix}{key}"
        if isinstance(value, dict):
            items.update(_flat_facts(value, flat_key + '.'))
        elif not isinstance(value, list):
            items[flat_key] = value
    return items


def _set_nested_value(d: dict, dotted_key: str, value) -> None:
    current = d
    parts = dotted_key.split('.')
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_fact_phrases(value: str) -> str:
    value = _strip_accents(str(value)).casefold()
    value = value.replace('&', ' and ')
    for pattern, replacement in FACT_SYNONYM_PHRASES:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value


def _canonical_text(value: str) -> str:
    value = _normalize_fact_phrases(value)
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in _canonical_text(value).split()
        if token not in FACT_COMPARISON_STOP_WORDS
    }


def _number_signature(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r'\d+(?:\.\d+)?', str(value)))


def _structure_component_signature(value: str) -> set[str]:
    normalized = _normalize_fact_phrases(value)
    return {
        component
        for component, pattern in STRUCTURE_COMPONENT_PATTERNS.items()
        if re.search(pattern, normalized, flags=re.IGNORECASE)
    }


def _comparison_decision(
    materially_changed: bool,
    confidence: float,
    reason: str,
    fact_value,
    preserve_existing: bool,
) -> FactComparisonDecision:
    return FactComparisonDecision(
        materially_changed=materially_changed,
        confidence=confidence,
        reason=reason,
        fact_value='' if fact_value is None else str(fact_value),
        preserve_existing=preserve_existing,
    )


def _deterministic_fact_comparison(
    fact_key: str,
    existing_value,
    observed_value,
) -> FactComparisonDecision | None:
    if existing_value == observed_value:
        return _comparison_decision(False, 1.0, "Values are identical.", existing_value, True)

    if existing_value in (None, '') or observed_value in (None, ''):
        return _comparison_decision(True, 1.0, "One value is missing.", observed_value, False)

    if not isinstance(existing_value, str) or not isinstance(observed_value, str):
        return _comparison_decision(True, 1.0, "Structured or numeric value changed.", observed_value, False)

    old_text = _canonical_text(existing_value)
    new_text = _canonical_text(observed_value)
    if old_text == new_text:
        return _comparison_decision(
            False,
            1.0,
            "Only punctuation, case, spelling, or separator formatting changed.",
            existing_value,
            True,
        )

    old_numbers = _number_signature(existing_value)
    new_numbers = _number_signature(observed_value)
    if old_numbers != new_numbers:
        return _comparison_decision(True, 1.0, "Numeric/date signature changed.", observed_value, False)

    if _is_location_fact(fact_key):
        if _meaningful_tokens(existing_value) == _meaningful_tokens(observed_value):
            return _comparison_decision(False, 1.0, "Location wording/order changed only.", existing_value, True)
        return _comparison_decision(True, 0.95, "Location set changed.", observed_value, False)

    if fact_key.endswith(('duration.de', 'duration.en')) and old_numbers:
        return _comparison_decision(False, 0.95, "Duration wording changed but numbers are stable.", existing_value, True)

    if fact_key.endswith(('structure.de', 'structure.en')):
        old_components = _structure_component_signature(existing_value)
        new_components = _structure_component_signature(observed_value)
        if old_components != new_components:
            return _comparison_decision(True, 0.95, "Programme structure component set changed.", observed_value, False)

        old_tokens = _meaningful_tokens(existing_value)
        new_tokens = _meaningful_tokens(observed_value)
        if old_tokens == new_tokens or old_tokens.issubset(new_tokens):
            return _comparison_decision(
                False,
                0.95,
                "Structure wording changed without changing numbers or components.",
                existing_value,
                True,
            )

    return None


def _is_descriptive_fact(key: str) -> bool:
    return key.endswith(DESCRIPTIVE_FACT_SUFFIXES)


def _is_location_fact(key: str) -> bool:
    return key.endswith(LOCATION_FACT_SUFFIXES)


def _is_non_material_text_change(key: str, old_value, new_value) -> bool:
    """Detect LLM wording drift for descriptive fields.

    The extraction is LLM-based, so prose fields can fluctuate between terse
    and verbose wording. Alerts should be driven by stable core facts, not
    punctuation, ordering, or added explanatory detail.
    """
    if not isinstance(old_value, str) or not isinstance(new_value, str):
        return False

    old_text = _canonical_text(old_value)
    new_text = _canonical_text(new_value)
    if old_text == new_text:
        return True

    if _is_location_fact(key):
        return _meaningful_tokens(old_value) == _meaningful_tokens(new_value)

    if not _is_descriptive_fact(key):
        return False

    old_tokens = _meaningful_tokens(old_value)
    new_tokens = _meaningful_tokens(new_value)
    if old_tokens and old_tokens.issubset(new_tokens):
        return True

    if key.endswith(('duration.de', 'duration.en')):
        old_numbers = _number_signature(old_value)
        new_numbers = _number_signature(new_value)
        return old_numbers == new_numbers and bool(old_numbers)

    return False


def _is_material_change(key: str, old_value, new_value) -> bool:
    if old_value == new_value:
        return False
    if _is_non_material_text_change(key, old_value, new_value):
        return False
    return True


def _source_keys_for_fact(programme_key: str, fact_key: str) -> list[str]:
    if fact_key.startswith('tuition_chf.') or 'deadline' in fact_key:
        return ['deadlines']
    if programme_key == 'emba':
        return ['emba', 'emba_plan']
    if programme_key == 'iemba':
        return ['iemba', 'iemba_es', 'iemba_plan']
    if programme_key == 'emba_x':
        return ['emba_x']
    return list(FACT_SOURCES)


def _snippet_for_fact(pages: dict[str, str], source_keys: list[str], observed_value) -> str:
    observed_tokens = [
        token for token in _meaningful_tokens(str(observed_value))
        if len(token) > 2
    ][:5]
    snippets = []
    for source_key in source_keys:
        text = pages.get(source_key, '') or ''
        if not text:
            continue
        canonical_text = _canonical_text(text)
        if observed_tokens and not all(token in canonical_text for token in observed_tokens[:2]):
            snippets.append(text[:3000])
            continue
        snippets.append(text[:3000])
    return "\n\n".join(snippets)[:8000]


def evaluate_fact_against_existing(
    existing_value,
    page_content: str,
    fact_key: str,
    source_info: str,
    language: str = '',
    observed_value=None,
) -> FactComparisonDecision:
    """Decide whether an extracted value is a material change from storage."""
    if observed_value is None:
        observed_value = page_content

    deterministic = _deterministic_fact_comparison(fact_key, existing_value, observed_value)
    if deterministic is not None:
        return deterministic

    try:
        from src.rag.models import ModelConfigurator
        model = ModelConfigurator.get_main_agent_model().with_structured_output(
            FactComparisonDecision
        )
        decision = model.invoke(FACT_COMPARISON_PROMPT.format(
            fact_key=fact_key,
            language=language or 'unknown',
            source_info=source_info,
            existing_value=existing_value,
            observed_value=observed_value,
            page_content=(page_content or '')[:8000],
        ))
        if decision.materially_changed:
            decision.preserve_existing = False
            decision.fact_value = str(observed_value)
        elif decision.preserve_existing:
            decision.fact_value = str(existing_value)
        return decision
    except Exception as exc:
        logger.warning(
            "Could not run LLM fact comparison for %s; preserving existing value "
            "to avoid an ambiguous overwrite: %s",
            fact_key,
            exc,
        )
        return _comparison_decision(
            False,
            0.0,
            "LLM comparison unavailable; ambiguous change preserved existing value.",
            existing_value,
            True,
        )


def preserve_materially_unchanged_extractions(
    old: dict,
    new: dict,
    pages: dict[str, str] | None = None,
) -> dict:
    """Compare extracted facts against stored facts before final diffing."""
    old_programmes = (old or {}).get('programmes', {})
    pages = pages or {}
    for prog_key, new_prog in new.get('programmes', {}).items():
        old_prog = old_programmes.get(prog_key, {})
        old_flat, new_flat = _flat_facts(old_prog), _flat_facts(new_prog)
        for key in sorted(set(old_flat) & set(new_flat)):
            if old_flat[key] == new_flat[key]:
                continue
            full_key = f"{prog_key}.{key}"
            source_keys = _source_keys_for_fact(prog_key, key)
            source_info = ", ".join(FACT_SOURCES[source_key] for source_key in source_keys if source_key in FACT_SOURCES)
            decision = evaluate_fact_against_existing(
                existing_value=old_flat[key],
                observed_value=new_flat[key],
                page_content=_snippet_for_fact(pages, source_keys, new_flat[key]),
                fact_key=full_key,
                source_info=source_info,
                language='de' if key.endswith('.de') else 'en' if key.endswith('.en') else '',
            )
            if decision.preserve_existing or not decision.materially_changed:
                logger.info(
                    "Preserving existing %s: %s",
                    full_key,
                    decision.reason,
                )
                _set_nested_value(new_prog, key, old_flat[key])
    return new


def preserve_non_material_changes(old: dict, new: dict) -> dict:
    """Keep existing wording when the new extraction is only a paraphrase."""
    old_programmes = (old or {}).get('programmes', {})
    for prog_key, new_prog in new.get('programmes', {}).items():
        old_prog = old_programmes.get(prog_key, {})
        old_flat, new_flat = _flat_facts(old_prog), _flat_facts(new_prog)
        for key in sorted(set(old_flat) & set(new_flat)):
            if old_flat[key] == new_flat[key]:
                continue
            full_key = f"{prog_key}.{key}"
            if not _is_material_change(full_key, old_flat[key], new_flat[key]):
                _set_nested_value(new_prog, key, old_flat[key])
    return new


def diff_facts(old: dict, new: dict) -> list[str]:
    """Compare volatile values between old and new facts; returns change lines."""
    changes = []
    old_programmes = (old or {}).get('programmes', {})
    for prog_key, new_prog in new.get('programmes', {}).items():
        old_prog = old_programmes.get(prog_key, {})

        old_flat, new_flat = _flat_facts(old_prog), _flat_facts(new_prog)
        for key in sorted(set(old_flat) | set(new_flat)):
            full_key = f"{prog_key}.{key}"
            if _is_material_change(full_key, old_flat.get(key), new_flat.get(key)):
                changes.append(
                    f"{prog_key}.{key}: {old_flat.get(key, '<missing>')} -> {new_flat.get(key, '<missing>')}"
                )
    return changes


def notify_changes(changes: list[str]) -> None:
    try:
        from src.notification.notification_center import NotificationCenter
        NotificationCenter().send_notification(
            subject="Programme facts changed on official websites",
            body="The fact checker detected changes:\n\n" + "\n".join(changes),
            channel="all",
        )
    except Exception as e:
        logger.warning(f"Could not send change notification: {e}")


# ----------------------------------- Main ------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Show diff without writing')
    args = parser.parse_args()

    old_facts = {}
    if os.path.exists(FACTS_PATH):
        with open(FACTS_PATH, encoding='utf-8') as f:
            old_facts = json.load(f)

    pages = fetch_sources()
    try:
        extracted = extract_facts(pages, existing_facts=old_facts)
    except Exception as exc:
        logger.error(f"Could not extract programme facts; existing facts file was not changed: {exc}")
        return 1

    extracted = apply_deterministic_fallbacks(extracted, pages)
    extracted = apply_deterministic_source_facts(extracted, pages)
    new_facts = to_facts_document(extracted)

    if old_facts:
        new_facts = preserve_materially_unchanged_extractions(old_facts, new_facts, pages)
        new_facts = preserve_non_material_changes(old_facts, new_facts)

    changes = diff_facts(old_facts, new_facts)
    if changes:
        logger.warning(f"Detected {len(changes)} fact change(s):")
        for change in changes:
            logger.warning(f"  {change}")
    else:
        logger.info("No fact changes detected.")

    if args.dry_run:
        print(json.dumps(new_facts, indent=2, ensure_ascii=False))
        return 0

    if old_facts and not changes:
        logger.info("Keeping existing facts file because only non-material wording changed.")
        return 0

    os.makedirs(os.path.dirname(FACTS_PATH), exist_ok=True)
    with open(FACTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(new_facts, f, indent=2, ensure_ascii=False)
    logger.info(f"Wrote {FACTS_PATH}")

    if changes:
        notify_changes(changes)

    # Invalidate the in-process cache so a running app picks up new facts
    try:
        from src.rag.verified_facts import VerifiedFacts
        VerifiedFacts.reset_cache()
    except Exception:
        pass

    return 0


if __name__ == '__main__':
    sys.exit(main())
