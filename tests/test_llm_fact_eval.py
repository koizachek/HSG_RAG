"""
LLM eval set: 30 fact questions (DE/EN) against the live agent chain.

Expected values are read dynamically from data/database/programme_facts.json, so the
eval stays valid after every facts regeneration. The core assertion per case:
the answer must contain the correct programme's value AND must NOT contain
another programme's value (cross-contamination guard — the historic bug).

Opt-in (costs API credits, needs OPENAI_API_KEY + Weaviate):
    RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v

Single case:
    RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v -k "de_price_emba"
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import config

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LLM_EVAL"),
    reason="LLM eval is opt-in: set RUN_LLM_EVAL=1",
)


def _facts() -> dict:
    path = os.path.join(config.paths.DATA, "database", "programme_facts.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["programmes"]


def _normalize(text: str) -> str:
    """Lowercase and strip thousand separators so CHF 77'500 / 77,500 / 77 500
    all normalize to '77500'."""
    text = text.lower()
    return re.sub(r"(?<=\d)[\s'’,.](?=\d{3}\b)", "", text)


def _fee(prog: str, which: str = "final_deadline") -> str:
    return str(_facts()[prog]["tuition_chf"][which]["fee"])


def _start_year(prog: str) -> str:
    return _facts()[prog]["programme_start"][:4]


def _ects(prog: str) -> str:
    return str(_facts()[prog]["ects_credits"])


# --------------------------------------------------------------------------
# Eval cases. Fields:
#   id            unique test id (language prefix included)
#   lang          conversation language the chain is initialized with
#   query         user question
#   expect_any    list of token-groups; AT LEAST ONE token of EVERY group
#                 must appear in the normalized answer
#   forbid        tokens that must NOT appear (cross-contamination guard)
# --------------------------------------------------------------------------

def build_cases() -> list[dict]:
    f = _facts()
    emba_fee, iemba_fee, embax_fee = _fee("emba"), _fee("iemba"), _fee("emba_x")
    emba_fee1, iemba_fee1, embax_fee1 = (
        _fee("emba", "first_deadline"),
        _fee("iemba", "first_deadline"),
        _fee("emba_x", "first_deadline"),
    )

    return [
        # ---------- Pricing (the historic hallucination hotspot) ----------
        dict(id="de_price_emba", lang="de",
             query="Was kostet der EMBA?",
             expect_any=[[emba_fee, emba_fee1]],
             forbid=[iemba_fee, embax_fee]),
        dict(id="de_price_iemba", lang="de",
             query="Was kostet der IEMBA?",
             expect_any=[[iemba_fee, iemba_fee1]],
             forbid=[emba_fee, embax_fee]),
        dict(id="de_price_embax", lang="de",
             query="Was kostet emba X?",
             expect_any=[[embax_fee, embax_fee1]],
             forbid=[emba_fee, iemba_fee]),
        dict(id="en_price_emba", lang="en",
             query="How much does the EMBA HSG cost?",
             expect_any=[[emba_fee, emba_fee1]],
             forbid=[iemba_fee, embax_fee]),
        dict(id="en_price_iemba", lang="en",
             query="What is the tuition fee for the IEMBA?",
             expect_any=[[iemba_fee, iemba_fee1]],
             forbid=[emba_fee, embax_fee]),
        dict(id="en_price_embax", lang="en",
             query="How much is the emba X programme?",
             expect_any=[[embax_fee, embax_fee1]],
             forbid=[emba_fee, iemba_fee]),
        dict(id="de_price_comparison", lang="de",
             query="Vergleiche bitte die Kosten aller drei Programme.",
             expect_any=[[emba_fee, emba_fee1], [iemba_fee, iemba_fee1], [embax_fee, embax_fee1]],
             forbid=[]),
        dict(id="en_price_deadline_logic", lang="en",
             query="If I apply for the EMBA now, which fee applies?",
             expect_any=[[emba_fee, emba_fee1]],
             forbid=[iemba_fee, embax_fee]),

        # ---------------------------- Deadlines ---------------------------
        dict(id="de_deadline_emba", lang="de",
             query="Bis wann kann ich mich für den EMBA bewerben?",
             expect_any=[["2026"]],
             forbid=[]),
        dict(id="en_deadline_embax", lang="en",
             query="What is the application deadline for emba X?",
             expect_any=[["august", "october", "2026"]],
             forbid=[]),
        dict(id="en_deadline_iemba_passed", lang="en",
             query="Can I still get the early-bird fee for the IEMBA?",
             expect_any=[[iemba_fee, "passed", "expired", "no longer", "final"]],
             forbid=[]),

        # ------------------------------ Starts -----------------------------
        dict(id="de_start_emba", lang="de",
             query="Wann startet der nächste EMBA?",
             expect_any=[[_start_year("emba")], ["september", "09"]],
             forbid=[]),
        dict(id="de_start_iemba", lang="de",
             query="Wann beginnt der IEMBA?",
             expect_any=[[_start_year("iemba")], ["august", "08"]],
             forbid=[]),
        dict(id="en_start_embax", lang="en",
             query="When does the next emba X cohort start?",
             expect_any=[[_start_year("emba_x")], ["february", "02"]],
             forbid=[]),

        # ----------------------------- Duration ----------------------------
        dict(id="de_duration_emba", lang="de",
             query="Wie lange dauert der deutschsprachige EMBA HSG?",
             expect_any=[["18"]],
             forbid=[]),
        dict(id="de_duration_emba_short_name", lang="de",
             query="Wie lange dauert der EMBA?",
             expect_any=[["iemba", "international"], ["emba x", "embax"]],
             forbid=[]),
        dict(id="en_duration_embax", lang="en",
             query="How long does the emba X take and how many ECTS is it?",
             expect_any=[["18"], [_ects("emba_x")]],
             forbid=[]),

        # ------------------------- Language / format -----------------------
        dict(id="de_language_iemba", lang="de",
             query="In welcher Sprache wird der IEMBA unterrichtet?",
             expect_any=[["englisch", "english"]],
             forbid=[]),
        dict(id="en_language_emba", lang="en",
             query="Is the EMBA HSG taught in English?",
             expect_any=[["german", "deutsch"]],
             forbid=[]),
        dict(id="de_locations_embax", lang="de",
             query="Wo findet emba X statt?",
             expect_any=[["zürich", "zurich"], ["st.gallen", "st. gallen", "gallen"]],
             forbid=[]),
        dict(id="en_structure_iemba", lang="en",
             query="How many weeks on campus and abroad does the IEMBA require?",
             expect_any=[["10"], ["4", "abroad"]],
             forbid=[]),

        # ----------------------------- Advisors ----------------------------
        dict(id="de_advisor_emba", lang="de",
             query="Wer ist meine Ansprechpartnerin für den EMBA?",
             expect_any=[["cyra", "von müller", "von mueller"]],
             forbid=["kristin", "teyuna"]),
        dict(id="en_advisor_iemba", lang="en",
             query="Who can I contact about the IEMBA?",
             expect_any=[["kristin", "fuchs"]],
             forbid=["cyra", "teyuna"]),
        dict(id="en_advisor_embax", lang="en",
             query="Who is the admissions contact for emba X?",
             expect_any=[["teyuna", "giger"]],
             forbid=["cyra", "kristin"]),

        # ----------------------- Grounding / honesty -----------------------
        dict(id="de_no_invented_accommodation", lang="de",
             query="Ist die Unterkunft in den Studiengebühren enthalten?",
             expect_any=[["nicht", "nein", "kein"]],
             forbid=[]),
        dict(id="en_no_price_range", lang="en",
             query="Roughly what price range do the HSG executive MBAs fall into?",
             expect_any=[[emba_fee, emba_fee1, iemba_fee, embax_fee]],
             forbid=["six-figure", "six figure", "sechsstellig"]),
        dict(id="de_unknown_fact_honesty", lang="de",
             query="Wie viele Parkplätze gibt es am Executive Campus?",
             expect_any=[["nicht", "keine", "admissions", "team", "leider"]],
             forbid=[]),

        # --------------------------- Conversational ------------------------
        dict(id="de_fit_question", lang="de",
             query="Ich bin Softwarearchitekt mit 12 Jahren Erfahrung, welches Programm passt zu mir?",
             expect_any=[["emba x", "embax", "emba"]],
             forbid=[]),
        dict(id="en_fit_question", lang="en",
             query="I lead international teams and want a global programme. Which one fits?",
             expect_any=[["iemba", "international"]],
             forbid=[]),
        dict(id="de_booking_intent", lang="de",
             query="Ich möchte gerne einen Beratungstermin für den IEMBA vereinbaren.",
             expect_any=[["termin", "beratung", "kristin"]],
             forbid=[]),
        dict(id="en_overview", lang="en",
             query="Give me a short overview of all three executive MBA programmes.",
             expect_any=[["emba"], ["iemba", "international"], ["emba x", "embax"]],
             forbid=[]),
    ]


CASES = build_cases() if os.getenv("RUN_LLM_EVAL") else []


@pytest.fixture(scope="module")
def make_chain():
    from src.rag.agent_chain import ExecutiveAgentChain

    def _factory(lang: str):
        return ExecutiveAgentChain(language=lang, session_id=f"eval_{lang}")

    return _factory


# Latency gate: a single turn must never exceed this (generous cap that still
# catches gross regressions such as switching back to a reasoning model).
MAX_TURN_SECONDS = 25.0


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_fact_eval(case, make_chain):
    from time import perf_counter

    chain = make_chain(case["lang"])
    turn_start = perf_counter()
    result = chain.query(case["query"])
    elapsed = perf_counter() - turn_start
    answer = _normalize(
        (result.response or "") + " " + (result.additional_details or "")
    )

    assert elapsed < MAX_TURN_SECONDS, (
        f"Latency regression: turn took {elapsed:.1f}s (cap {MAX_TURN_SECONDS}s) "
        f"for: {case['query']}"
    )

    assert answer.strip(), f"Empty answer for: {case['query']}"

    for group in case["expect_any"]:
        assert any(_normalize(tok) in answer for tok in group), (
            f"\nQuery:    {case['query']}"
            f"\nExpected one of: {group}"
            f"\nAnswer:   {answer[:600]}"
        )

    for forbidden in case["forbid"]:
        assert _normalize(forbidden) not in answer, (
            f"\nQuery:    {case['query']}"
            f"\nFORBIDDEN token found (cross-programme contamination): {forbidden}"
            f"\nAnswer:   {answer[:600]}"
        )
