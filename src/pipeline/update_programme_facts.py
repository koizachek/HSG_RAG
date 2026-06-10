"""
Regenerate data/programme_facts.json from the official programme websites.

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
import sys
from datetime import date

import requests
from pydantic import BaseModel, Field

from src.config import config
from src.utils.logging import get_logger

logger = get_logger('update_programme_facts')

FACTS_PATH = os.path.join(config.paths.DATA, 'programme_facts.json')

# Pages that contain the volatile core facts (tuition, deadlines, starts).
FACT_SOURCES = {
    'overview':  'https://emba.unisg.ch/',
    'deadlines': 'https://emba.unisg.ch/bewerbung/fristen',
    'emba':      'https://emba.unisg.ch/programm/emba',
    'iemba':     'https://emba.unisg.ch/programm/iemba',
    'emba_x':    'https://embax.ch/',
}

REQUEST_TIMEOUT = 30
USER_AGENT = 'HSG-RAG-FactChecker/1.0 (+https://emba.unisg.ch)'


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
- Dates in ISO format (14. September 2026 -> 2026-09-14).
- Never mix values between programmes. The deadlines page contains one row
  per programme - keep them strictly separated.

PAGE CONTENT:
{page_content}"""


# --------------------------------- Fetching ----------------------------------

def fetch_sources() -> dict[str, str]:
    """Fetch all fact source pages. Raises when a page cannot be fetched."""
    pages = {}
    for key, url in FACT_SOURCES.items():
        logger.info(f"Fetching {url}")
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers={'User-Agent': USER_AGENT})
        resp.raise_for_status()
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


def to_facts_document(extracted: AllProgrammesSchema) -> dict:
    """Convert the extraction schema into the programme_facts.json layout."""
    def programme(p: ProgrammeFactsSchema, source_urls: list[str]) -> dict:
        return {
            'official_name': p.official_name,
            'current_cohort': p.current_cohort,
            'language': p.language.model_dump(),
            'programme_start': p.programme_start,
            'duration': p.duration.model_dump(),
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
            'emba': programme(extracted.emba, [FACT_SOURCES['emba'], FACT_SOURCES['deadlines']]),
            'iemba': programme(extracted.iemba, [FACT_SOURCES['iemba'], FACT_SOURCES['deadlines']]),
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
