"""
UAT acceptance gate: run the chatbot through workbook scenarios and judge the
full conversation with an LLM.

Opt-in because this calls live LLMs and Weaviate:
    RUN_UAT_LLM_JUDGE=1 pytest tests/test_uat_llm_judge.py -v -s
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import config
from src.rag.agent_chain import ExecutiveAgentChain


DEFAULT_EXCEL = Path(__file__).resolve().parent / "fixtures" / "UAT.xlsx"
SKIPPED_SHEETS = {"About", "TestProtocol", "Reporting"}
DEFAULT_JUDGE_MODEL = os.getenv("UAT_JUDGE_MODEL", "gpt-4o-mini")
MIN_ACCEPTABLE_SCORE = float(os.getenv("UAT_MIN_SCORE", "7.0"))


@dataclass(frozen=True)
class UATCase:
    case_id: str
    sheet: str
    title: str
    persona: list[str] = field(default_factory=list)
    user_turns: list[str] = field(default_factory=list)
    expected_bot_behaviour: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    expected_language: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "sheet": self.sheet,
            "title": self.title,
            "persona": self.persona,
            "user_turns": self.user_turns,
            "expected_bot_behaviour": self.expected_bot_behaviour,
            "success_criteria": self.success_criteria,
            "red_flags": self.red_flags,
            "expected_language": self.expected_language,
        }


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _infer_expected_language(*texts: str) -> str | None:
    joined = "\n".join(texts).lower()
    if "websiteaufruf auf deutsch" in joined or "sprache: deutsch" in joined:
        return "de"
    if (
        "websiteaufruf auf englisch" in joined
        or "sprache: englisch" in joined
        or "sprache: english" in joined
    ):
        return "en"
    if "deutsch" in joined or "german" in joined:
        return "de"
    if "englisch" in joined or "english" in joined:
        return "en"
    return None


def _case_blocks(ws) -> list[tuple[int, int]]:
    starts = []
    for row_idx in range(1, ws.max_row + 1):
        if _cell_text(ws.cell(row_idx, 1).value).startswith("TC-"):
            starts.append(row_idx)

    blocks = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] - 1 if idx + 1 < len(starts) else ws.max_row
        blocks.append((start, end))
    return blocks


def _find_header_columns(ws, markers: tuple[str, ...]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for row in ws.iter_rows():
        for cell in row:
            text = _cell_text(cell.value).lower()
            for marker in markers:
                if marker.lower() in text and marker not in columns:
                    columns[marker] = cell.column
    return columns


def parse_uat_excel(path: Path = DEFAULT_EXCEL) -> list[UATCase]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to parse tests/fixtures/UAT.xlsx") from exc

    workbook = openpyxl.load_workbook(path, data_only=True)
    cases: list[UATCase] = []

    for ws in workbook.worksheets:
        if ws.title in SKIPPED_SHEETS:
            continue

        header_columns = _find_header_columns(ws, ("Success Criteria", "Red Flags"))
        success_col = header_columns.get("Success Criteria")
        red_col = header_columns.get("Red Flags")

        for start, end in _case_blocks(ws):
            title = _cell_text(ws.cell(start, 1).value)
            case_id_match = re.search(r"(TC-[A-Z0-9-]+)", title)
            case_id = case_id_match.group(1) if case_id_match else f"{ws.title}-{start}"

            flow_row = None
            for row_idx in range(start, end + 1):
                row_values = [_cell_text(ws.cell(row_idx, col).value).lower() for col in range(1, 4)]
                if "dialog flow" in row_values:
                    flow_row = row_idx
                    break

            persona = []
            persona_end = (flow_row - 1) if flow_row else end
            for row_idx in range(start + 1, persona_end + 1):
                text = _cell_text(ws.cell(row_idx, 1).value)
                if text and text.lower() not in {"persona", "dialog flow"} and not text.startswith("TC-"):
                    persona.append(text)

            user_turns = []
            expected = []
            action_texts = []
            for row_idx in range((flow_row or start) + 1, end + 1):
                user_text = _cell_text(ws.cell(row_idx, 2).value)
                bot_text = _cell_text(ws.cell(row_idx, 3).value)
                if user_text:
                    if user_text.startswith("(Aktion)"):
                        action_texts.append(user_text)
                    else:
                        user_turns.append(user_text)
                if bot_text:
                    expected.append(bot_text)

            if not user_turns:
                continue

            success = []
            if success_col:
                for row_idx in range(start, end + 1):
                    text = _cell_text(ws.cell(row_idx, success_col).value)
                    if text and not text.lower().startswith(("success criteria", "key features", "positionierung")):
                        success.append(text)

            red_flags = []
            if red_col:
                for row_idx in range(start, end + 1):
                    text = _cell_text(ws.cell(row_idx, red_col).value)
                    if text and not text.lower().startswith("red flags"):
                        red_flags.append(text)

            expected_language = _infer_expected_language(
                ws.title,
                title,
                "\n".join(persona),
                "\n".join(action_texts),
                "\n".join(user_turns),
                "\n".join(success),
            )
            cases.append(
                UATCase(
                    case_id=case_id,
                    sheet=ws.title,
                    title=title,
                    persona=persona,
                    user_turns=user_turns,
                    expected_bot_behaviour=expected,
                    success_criteria=success,
                    red_flags=red_flags,
                    expected_language=expected_language,
                )
            )

    return cases


def _selected_cases() -> list[UATCase]:
    cases = parse_uat_excel()
    limit = int(os.getenv("UAT_LIMIT", "0") or "0")
    if limit > 0:
        return cases[:limit]
    return cases


def _hard_facts() -> dict[str, Any]:
    path = Path(config.paths.DATA) / "database" / "programme_facts.json"
    with path.open(encoding="utf-8") as f:
        facts = json.load(f)

    programmes = {}
    for key, programme in facts["programmes"].items():
        tuition = programme["tuition_chf"]
        programmes[key] = {
            "official_name": programme["official_name"],
            "language": programme["language"],
            "programme_start": programme["programme_start"],
            "duration": programme["duration"],
            "ects_credits": programme["ects_credits"],
            "structure": programme["structure"],
            "locations": programme["locations"],
            "tuition_chf": {
                "first_deadline": tuition["first_deadline"],
                "final_deadline": tuition["final_deadline"],
                "note": tuition.get("note", {}),
            },
            "advisor": programme["advisor"],
        }
    return {"programmes": programmes}


def _run_chatbot_case(case: UATCase) -> list[dict[str, Any]]:
    chain = ExecutiveAgentChain(
        language=case.expected_language or "en",
        session_id=f"uat-{case.case_id}-{uuid.uuid4()}",
    )

    transcript = []
    for turn_index, query in enumerate(case.user_turns, start=1):
        started = time.perf_counter()
        result = chain.query(query)
        transcript.append(
            {
                "turn": turn_index,
                "user": query,
                "assistant": result.response,
                "additional_details": result.additional_details or "",
                "language": result.language,
                "appointment_requested": result.appointment_requested,
                "show_booking_widget": result.show_booking_widget,
                "relevant_programs": result.relevant_programs,
                "elapsed_s": round(time.perf_counter() - started, 3),
            }
        )
    return transcript


def _openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai is required for the UAT LLM judge.") from exc

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_COMPAT_API_KEY")
    base_url = os.getenv("OPENAI_COMPAT_BASE_URL")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY for RUN_UAT_LLM_JUDGE=1.")

    kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": float(os.getenv("UAT_JUDGE_TIMEOUT_S", "120")),
    }
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _judge_case(case: UATCase, transcript: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "scenario": case.to_payload(),
        "hard_facts_current_source_of_truth": _hard_facts(),
        "transcript": transcript,
        "minimum_acceptable_score": MIN_ACCEPTABLE_SCORE,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are a strict but fair UAT judge for the HSG Executive Education chatbot. "
                "Evaluate the whole transcript against the scenario, success criteria, red flags, "
                "and current hard facts. Current hard facts override stale scenario wording. "
                "Do not require exact phrasing. Reward helpful, grounded, concise advisory answers. "
                "Penalize wrong programme facts, wrong language, unsupported promises, hidden/internal "
                "architecture talk, missed booking or handover behavior, and rude tone. "
                "Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "Score this UAT transcript from 0 to 10. "
                "Return JSON with keys: overall_score, passed, verdict, strengths, issues, "
                "criteria_met, criteria_missed, language_ok, factuality_ok, tone_ok.\n\n"
                f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
            ),
        },
    ]

    client = _openai_client()
    completion = client.chat.completions.create(
        model=DEFAULT_JUDGE_MODEL,
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = completion.choices[0].message.content or "{}"
    return json.loads(content)


UAT_CASES = _selected_cases()


@pytest.mark.network
@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_UAT_LLM_JUDGE") != "1",
    reason="Set RUN_UAT_LLM_JUDGE=1 to run live UAT conversations and LLM judge.",
)
@pytest.mark.parametrize("case", UAT_CASES, ids=[case.case_id for case in UAT_CASES])
def test_uat_case_passes_llm_judge(case: UATCase):
    transcript = _run_chatbot_case(case)
    judgement = _judge_case(case, transcript)
    score = float(judgement.get("overall_score", 0))

    assert score >= MIN_ACCEPTABLE_SCORE and judgement.get("passed", True), (
        f"\nUAT case: {case.case_id} - {case.title}"
        f"\nScore: {score} (minimum {MIN_ACCEPTABLE_SCORE})"
        f"\nVerdict: {judgement.get('verdict')}"
        f"\nIssues: {json.dumps(judgement.get('issues', []), ensure_ascii=False)}"
        f"\nCriteria missed: {json.dumps(judgement.get('criteria_missed', []), ensure_ascii=False)}"
        f"\nTranscript: {json.dumps(transcript, ensure_ascii=False, indent=2)}"
    )


def test_uat_workbook_contains_cases():
    assert len(parse_uat_excel()) > 0
