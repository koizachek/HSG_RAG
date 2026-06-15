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
import json
import os
import re
import sys
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

PAGE CONTENT:
{page_content}"""


# --------------------------------- Fetching ----------------------------------

def extract_pdf_text(content: bytes, url: str) -> str:
    """Extract text from a PDF response using the existing docling dependency."""
    suffix = os.path.splitext(url)[1] or '.pdf'
    with NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(tmp_path)
        return result.document.export_to_markdown()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


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
            pages[key] = extract_pdf_text(resp.content, url)
            continue
        # Lightweight HTML -> text. The scraping pipeline has richer
        # processors; for fact extraction visible text is sufficient.
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tag in soup(['script', 'style', 'noscript']):
                tag.decompose()
            pages[key] = soup.get_text(separator='\n', strip=True)
        except ImportError:
            pages[key] = resp.text
    return pages


# -------------------------------- Extraction ---------------------------------

def extract_facts(pages: dict[str, str]) -> AllProgrammesSchema:
    """LLM-based structured extraction over the fetched pages."""
    from src.rag.models import ModelConfigurator
    model = ModelConfigurator.get_main_agent_model().with_structured_output(
        AllProgrammesSchema
    )
    page_content = "\n\n".join(
        f"===== SOURCE: {FACT_SOURCES[key]} =====\n{text[:20000]}"
        for key, text in pages.items()
    )
    return model.invoke(EXTRACTION_PROMPT.format(page_content=page_content))


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

def diff_facts(old: dict, new: dict) -> list[str]:
    """Compare volatile values between old and new facts; returns change lines."""
    changes = []
    old_programmes = (old or {}).get('programmes', {})
    for prog_key, new_prog in new.get('programmes', {}).items():
        old_prog = old_programmes.get(prog_key, {})

        def flat(d, prefix=''):
            items = {}
            for k, v in (d or {}).items():
                key = f"{prefix}{k}"
                if isinstance(v, dict):
                    items.update(flat(v, key + '.'))
                elif not isinstance(v, list):
                    items[key] = v
            return items

        old_flat, new_flat = flat(old_prog), flat(new_prog)
        for key in sorted(set(old_flat) | set(new_flat)):
            if old_flat.get(key) != new_flat.get(key):
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

    pages = fetch_sources()
    extracted = extract_facts(pages)
    extracted = apply_deterministic_fallbacks(extracted, pages)
    new_facts = to_facts_document(extracted)

    old_facts = {}
    if os.path.exists(FACTS_PATH):
        with open(FACTS_PATH, encoding='utf-8') as f:
            old_facts = json.load(f)

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
