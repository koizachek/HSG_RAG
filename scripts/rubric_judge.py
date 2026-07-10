#!/usr/bin/env python3
"""Offline rubric scoring of stored conversation transcripts.

Runs ON THE PROD HOST, inside the app container (which has the openai package
and OPEN_ROUTER_API_KEY), so transcripts never leave the host:

    docker exec hsg-rag python scripts/rubric_judge.py \
        --transcripts-dir logs/transcripts \
        --out logs/usage_reports/rubric_scores.json \
        --window-days 7

Scores a deterministic weekly sample of conversations 0-10 on: helpfulness,
grounding, tone, conversion_support, language_consistency — plus flags from a
CLOSED vocabulary (so no conversation text can leak into downstream reports).
The output JSON stays host-only; scripts/usage_report.py ingests only its
aggregates and flag counts.

Judging sends sampled transcripts to the LLM judge via OpenRouter — the same
processing basis as live traffic (documented for the DSB). If the transcripts
directory is missing or empty (transcript storage disabled), writes
{"sampled": 0} and exits 0.
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = os.getenv("USAGE_RUBRIC_JUDGE_MODEL", "openai/gpt-4o-mini")
DEFAULT_SAMPLE = int(os.getenv("USAGE_RUBRIC_SAMPLE_SIZE", "10"))
PARSE_ATTEMPTS = 3

RUBRIC_DIMENSIONS = [
    "helpfulness",
    "grounding",
    "tone",
    "conversion_support",
    "language_consistency",
]
FLAG_VOCABULARY = [
    "possible_hallucination",
    "wrong_programme_fact",
    "missed_booking_opportunity",
    "unresolved_user_need",
    "rude_tone",
    "language_switch_error",
    "other",
]

JUDGE_SYSTEM_PROMPT = f"""You are a strict but fair quality judge for the HSG Executive Education \
advisory chatbot (programmes: EMBA HSG, IEMBA, emba X). You receive one real \
(pseudonymized) conversation transcript. Score the ASSISTANT's overall \
performance across the whole conversation on these dimensions, each 0-10:

- helpfulness: does the user get substantive, specific, actionable answers?
- grounding: are programme claims plausible and consistent; penalize likely \
invented facts, prices or deadlines, and confident answers where the assistant \
should have acknowledged missing information.
- tone: professional, warm, concise; no hype (never "best/world-class/perfect"), \
no rudeness, no patronizing repetition.
- conversion_support: when (and only when) the user shows readiness or asks, \
is a clear advisor/booking path offered? Booking is user-led by design - do \
NOT reward pushy unsolicited offers, and do NOT penalize their absence on \
purely informational turns.
- language_consistency: replies stay in the user's language (German or English) \
unless the user switches.

Also return "flags": a list drawn ONLY from this closed vocabulary (empty list \
if none apply): {json.dumps(FLAG_VOCABULARY)}.

Return ONLY valid JSON: {{"scores": {{"helpfulness": n, "grounding": n, "tone": n, \
"conversion_support": n, "language_consistency": n}}, "flags": [...]}}"""


def _client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required for rubric judging") from exc
    api_key = os.environ.get("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPEN_ROUTER_API_KEY is required for rubric judging")
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=120.0)


def read_transcript(path: Path) -> list[dict]:
    turns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            turns.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return sorted(turns, key=lambda t: t.get("turn_index", 0))


def judge_transcript(client, model: str, turns: list[dict]) -> dict | None:
    conversation = [
        {"turn": t.get("turn_index"), "user": t.get("user"), "assistant": t.get("assistant")}
        for t in turns
    ]
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"transcript": conversation}, ensure_ascii=False)},
    ]
    for _ in range(PARSE_ATTEMPTS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        try:
            verdict = json.loads(response.choices[0].message.content)
            scores = verdict.get("scores") or {}
            if all(dim in scores for dim in RUBRIC_DIMENSIONS):
                flags = [f for f in (verdict.get("flags") or []) if f in FLAG_VOCABULARY]
                return {
                    "scores": {dim: float(scores[dim]) for dim in RUBRIC_DIMENSIONS},
                    "flags": flags,
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcripts-dir", default="logs/transcripts")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.window_days)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    transcripts_dir = Path(args.transcripts_dir)
    candidates = (
        [
            f
            for f in sorted(transcripts_dir.glob("transcript_*.jsonl"))
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) >= cutoff
        ]
        if transcripts_dir.is_dir()
        else []
    )

    if not candidates:
        out_path.write_text(
            json.dumps({"sampled": 0, "generated_at": now.isoformat()}), encoding="utf-8"
        )
        print("No transcripts in window (storage disabled or no traffic) — wrote sampled=0.")
        return 0

    # Deterministic weekly sample: reproducible re-runs within the same ISO week
    rng = random.Random(now.strftime("%G-W%V"))
    sample = (
        candidates
        if len(candidates) <= args.sample
        else rng.sample(candidates, args.sample)
    )
    skipped = len(candidates) - len(sample)
    if skipped:
        print(f"Sampling {len(sample)} of {len(candidates)} transcripts ({skipped} not judged).")

    client = _client()
    per_session = []
    for path in sample:
        turns = read_transcript(path)
        if not turns:
            continue
        verdict = judge_transcript(client, args.model, turns)
        if verdict is None:
            print(f"WARNING: judge returned no valid verdict for {path.name}", file=sys.stderr)
            continue
        per_session.append(
            {"session_id": turns[0].get("session_id", path.stem), **verdict}
        )

    aggregates = {}
    for dim in RUBRIC_DIMENSIONS:
        values = [s["scores"][dim] for s in per_session]
        if values:
            aggregates[dim] = {
                "mean": round(sum(values) / len(values), 2),
                "min": min(values),
            }
    flag_counts: dict[str, int] = {}
    for s in per_session:
        for flag in s["flags"]:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    result = {
        "generated_at": now.isoformat(),
        "window_days": args.window_days,
        "model": args.model,
        "sampled": len(per_session),
        "aggregates": aggregates,
        "flag_counts": flag_counts,
        # host-only detail (session ids never reach the markdown/JSON report)
        "sessions": per_session,
    }
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Judged {len(per_session)} transcripts -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
