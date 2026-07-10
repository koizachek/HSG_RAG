#!/usr/bin/env python3
"""Anonymous usage report over the HSG_RAG logs directory.

Usage:
    python3 scripts/usage_report.py --logs-dir /opt/hsg-rag/logs --window-days 7 \
        --out /opt/hsg-rag/logs/usage_reports/latest.md \
        [--json /opt/hsg-rag/logs/usage_reports/latest.json] \
        [--rubric-scores /opt/hsg-rag/logs/usage_reports/rubric_scores.json]

Primary source (structured, session-keyed, final post-gate flags):
  <logs>/usage/usage_<session_id>.jsonl      one JSON event per user turn
Legacy fallback when the window has no structured events (pre-gate caveat):
  <logs>/consent/*.jsonl, <logs>/user_profiles/profile_*.json, <logs>/logs.log

Output is aggregate counts/rates ONLY — no session ids, no names, no query or
answer text ever appears in the report (GDPR). Rubric scores, if provided, are
ingested as aggregates + closed-vocabulary flag counts only.

Stdlib only, so it runs with the host python3 outside the container.
"""
import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOW_TRAFFIC_SESSIONS = 5


# --------------------------- shared parsing helpers ---------------------------

def read_jsonl_objects(path: Path):
    """Read JSON objects from a file that is either strict one-line JSONL
    (usage events) or pretty-printed JSON objects back to back (consent files).

    Strict line-by-line parsing is tried first — the '}\\n{' blob split would
    corrupt one-line events that contain nested objects. The split fallback
    only handles the legacy pretty-printed consent format."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    objs = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objs.append(json.loads(line))
        except json.JSONDecodeError:
            objs = None
            break
    if objs is not None:
        return objs

    # Legacy fallback: pretty-printed JSON objects back to back
    objs = []
    for chunk in re.split(r"}\s*{", text):
        if not chunk.startswith("{"):
            chunk = "{" + chunk
        if not chunk.rstrip().endswith("}"):
            chunk = chunk + "}"
        try:
            objs.append(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    return objs


def _parse_ts(value: str):
    try:
        when = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def _percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1))))
    return ordered[k]


def _rate(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else f"{n}/0 (n/a)"


# ------------------------------ metric collection -----------------------------

def collect_consent(root: Path, cutoff: datetime) -> dict:
    decisions = Counter()
    by_policy = defaultdict(Counter)
    consent_dir = root / "consent"
    if consent_dir.is_dir():
        for f in sorted(consent_dir.glob("*.jsonl")):
            for obj in read_jsonl_objects(f):
                when = _parse_ts(obj.get("timestamp", ""))
                if when is None or when < cutoff:
                    continue
                decision = obj.get("decision", "unknown")
                decisions[decision] += 1
                by_policy[str(obj.get("policy_version", "?"))][decision] += 1
    return {
        "accepted": decisions.get("accepted", 0),
        "declined": decisions.get("declined", 0),
        "by_policy_version": {k: dict(v) for k, v in sorted(by_policy.items())},
    }


def collect_events(root: Path, cutoff: datetime) -> list[dict]:
    events = []
    usage_dir = root / "usage"
    if usage_dir.is_dir():
        for f in sorted(usage_dir.glob("usage_*.jsonl")):
            for obj in read_jsonl_objects(f):
                when = _parse_ts(obj.get("timestamp", ""))
                if when is None or when < cutoff:
                    continue
                events.append(obj)
    return events


def collect_i4_crosscheck(root: Path, cutoff: datetime) -> int:
    """Count 'falling back to blocking invoke' lines in logs.log within the
    window (I4 streaming-regression cross-check against the event flag)."""
    line_re = re.compile(r"^\((\d{4}\.\d{2}\.\d{2}) \d{2}:\d{2}:\d{2}\)")
    count = 0
    log_file = root / "logs.log"
    if log_file.exists():
        with log_file.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "falling back to blocking invoke" not in line:
                    continue
                m = line_re.match(line)
                if m:
                    day = datetime.strptime(m.group(1), "%Y.%m.%d").replace(
                        tzinfo=timezone.utc
                    )
                    if day < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                        continue
                count += 1
    return count


def collect_metrics(logs_dir: str, window_days: int = 7, now: datetime | None = None) -> dict:
    root = Path(logs_dir)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    consent = collect_consent(root, cutoff)
    events = collect_events(root, cutoff)

    metrics: dict = {
        "generated_at": now.isoformat(),
        "window_days": window_days,
        "source": "events" if events else "legacy",
        "consent": consent,
        "i4_blocking_fallback_log_lines": collect_i4_crosscheck(root, cutoff),
    }

    if events:
        metrics.update(_metrics_from_events(events))
    else:
        metrics.update(_metrics_legacy(root, cutoff))

    transcripts_dir = root / "transcripts"
    metrics["transcripts_in_window"] = (
        sum(
            1
            for f in transcripts_dir.glob("transcript_*.jsonl")
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) >= cutoff
        )
        if transcripts_dir.is_dir()
        else 0
    )
    return metrics


def _metrics_from_events(events: list[dict]) -> dict:
    sessions = defaultdict(list)
    for e in events:
        sessions[e.get("session_id") or "unknown"].append(e)

    outcome_counts = Counter(e.get("outcome", "unknown") for e in events)
    language_counts = Counter(e.get("language") or "unknown" for e in events)
    scope_types = Counter(
        e.get("scope_type") for e in events if e.get("scope_type")
    )

    def final(e, key):
        return bool((e.get("final") or {}).get(key))

    def pre(e, key):
        return bool((e.get("pre_gate") or {}).get(key))

    widget_turns = sum(1 for e in events if final(e, "show_booking_widget"))
    appointment_turns = sum(1 for e in events if final(e, "appointment_requested"))
    widget_sessions = sum(
        1 for evs in sessions.values() if any(final(e, "show_booking_widget") for e in evs)
    )
    appointment_sessions = sum(
        1
        for evs in sessions.values()
        if any(final(e, "appointment_requested") for e in evs)
    )
    handover_sessions = sum(
        1
        for evs in sessions.values()
        if any(e.get("handover_requested") is True for e in evs)
    )

    gate_suppressed = sum(
        1
        for e in events
        if e.get("pre_gate") is not None
        and pre(e, "show_booking_widget")
        and not final(e, "show_booking_widget")
    )
    gate_granted = sum(
        1
        for e in events
        if e.get("pre_gate") is not None
        and not pre(e, "show_booking_widget")
        and final(e, "show_booking_widget")
    )

    programme_turns = Counter()
    for e in events:
        for prog in (e.get("final") or {}).get("relevant_programs") or []:
            programme_turns[prog] += 1
    suggested = Counter()
    for evs in sessions.values():
        last = max(evs, key=lambda e: e.get("turn_index", 0))
        if last.get("suggested_program"):
            suggested[last["suggested_program"]] += 1

    turns_per_session = [len(evs) for evs in sessions.values()]
    total_s = [
        (e.get("timing") or {}).get("total_s")
        for e in events
        if (e.get("timing") or {}).get("total_s") is not None
    ]
    first_token_s = [
        (e.get("timing") or {}).get("first_token_s")
        for e in events
        if (e.get("timing") or {}).get("first_token_s") is not None
    ]
    preprocess_s = [
        (e.get("timing") or {}).get("preprocess_s")
        for e in events
        if (e.get("timing") or {}).get("preprocess_s") is not None
    ]

    return {
        "sessions": len(sessions),
        "turns": len(events),
        "turns_per_session_mean": round(statistics.mean(turns_per_session), 2)
        if turns_per_session
        else None,
        "turns_per_session_median": statistics.median(turns_per_session)
        if turns_per_session
        else None,
        "language_turns": dict(language_counts),
        "outcomes": dict(outcome_counts),
        "funnel": {
            "widget_shown_turns": widget_turns,
            "widget_shown_sessions": widget_sessions,
            "appointment_requested_turns": appointment_turns,
            "appointment_requested_sessions": appointment_sessions,
            "handover_sessions": handover_sessions,
            "gate_suppressed_turns": gate_suppressed,
            "gate_granted_turns": gate_granted,
            "programme_turns": dict(programme_turns),
            "suggested_program_sessions": dict(suggested),
        },
        "risks": {
            "agent_invoke_failed_turns": sum(
                1 for e in events if e.get("agent_invoke_failed")
            ),
            "streaming_fallback_turns": sum(
                1 for e in events if e.get("streaming_fallback")
            ),
            "retrieval_empty_turns": sum(1 for e in events if e.get("retrieval_empty")),
            "scope_redirect_turns": outcome_counts.get("scope_redirect", 0),
            "scope_types": dict(scope_types),
            "invalid_input_turns": outcome_counts.get("invalid_input", 0)
            + outcome_counts.get("repeated_invalid_input", 0),
            "max_turns_endings": outcome_counts.get("max_turns", 0),
            "exception_turns": outcome_counts.get("exception", 0),
            "slow_turns_over_15s": sum(1 for v in total_s if v > 15),
        },
        "latency": {
            "total_s_p50": _percentile(total_s, 50),
            "total_s_p90": _percentile(total_s, 90),
            "total_s_p99": _percentile(total_s, 99),
            "first_token_s_p50": _percentile(first_token_s, 50),
            "first_token_s_p90": _percentile(first_token_s, 90),
            "preprocess_s_p50": _percentile(preprocess_s, 50),
        },
    }


def _metrics_legacy(root: Path, cutoff: datetime) -> dict:
    """Fallback for windows before structured usage events existed.

    PRE-GATE CAVEAT: 'Show Booking Widget: True' / 'Appointment Requested:
    True' lines in logs.log are the model's RAW flags logged BEFORE the
    post-processing booking gate — model intent, not widgets actually shown.
    """
    sessions_with_profile = set()
    sessions_handover = set()
    suggested = Counter()
    latest_by_session: dict = {}
    profile_dir = root / "user_profiles"
    if profile_dir.is_dir():
        for f in profile_dir.glob("profile_*.json"):
            m = re.match(r"profile_(.+)_(\d{8}_\d{6})\.json$", f.name)
            if not m:
                continue
            sid, stamp = m.group(1), m.group(2)
            when = datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            if when < cutoff:
                continue
            if sid not in latest_by_session or stamp > latest_by_session[sid][0]:
                latest_by_session[sid] = (stamp, f)
    for sid, (_, f) in latest_by_session.items():
        try:
            prof = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        sessions_with_profile.add(sid)
        if prof.get("handover") is True:
            sessions_handover.add(sid)
        if prof.get("suggested_program"):
            suggested[prof["suggested_program"]] += 1

    line_re = re.compile(r"^\((\d{4}\.\d{2}\.\d{2}) \d{2}:\d{2}:\d{2}\)")
    counters = Counter()
    log_file = root / "logs.log"
    if log_file.exists():
        with log_file.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = line_re.match(line)
                if m:
                    day = datetime.strptime(m.group(1), "%Y.%m.%d").replace(
                        tzinfo=timezone.utc
                    )
                    if day < cutoff.replace(hour=0, minute=0, second=0, microsecond=0):
                        continue
                if "Show Booking Widget: True" in line:
                    counters["pre_gate_widget_turns"] += 1
                elif "Appointment Requested: True" in line:
                    counters["pre_gate_appointment_turns"] += 1
                elif "Proactive booking offer triggered" in line:
                    counters["gate_granted_turns"] += 1
                elif "Suppressed booking state" in line:
                    counters["gate_suppressed_turns"] += 1
                elif "Processing user query:" in line:
                    counters["user_turns"] += 1

    return {
        "sessions": len(sessions_with_profile),
        "turns": counters["user_turns"],
        "turns_per_session_mean": None,
        "turns_per_session_median": None,
        "language_turns": {},
        "outcomes": {},
        "funnel": {
            "pre_gate_widget_turns": counters["pre_gate_widget_turns"],
            "pre_gate_appointment_turns": counters["pre_gate_appointment_turns"],
            "gate_suppressed_turns": counters["gate_suppressed_turns"],
            "gate_granted_turns": counters["gate_granted_turns"],
            "handover_sessions": len(sessions_handover),
            "programme_turns": {},
            "suggested_program_sessions": dict(suggested),
        },
        "risks": {},
        "latency": {},
    }


# --------------------------------- rendering ----------------------------------

def _fmt(value, suffix=""):
    return f"{value}{suffix}" if value is not None else "n/a"


def render_markdown(metrics: dict, rubric: dict | None = None) -> str:
    consent = metrics["consent"]
    accepted, declined = consent["accepted"], consent["declined"]
    total_consent = accepted + declined
    funnel = metrics.get("funnel", {})
    risks = metrics.get("risks", {})
    latency = metrics.get("latency", {})
    sessions = metrics.get("sessions", 0)
    generated_day = metrics["generated_at"][:10]
    week = datetime.fromisoformat(metrics["generated_at"]).strftime("%G-W%V")

    lines = [
        f"# Usage Report — Week {week}",
        "",
        f"- Period: last {metrics['window_days']} days (generated {generated_day})",
        f"- Data basis: {'structured usage events' if metrics['source'] == 'events' else 'LEGACY log parsing (pre-gate caveat applies)'}",
        "- Content: anonymous aggregates only — no session ids, no conversation text",
        "",
        "## 1. Traffic & Funnel",
        "",
        f"- Consent decisions: {total_consent} — accepted {_rate(accepted, total_consent)}",
    ]
    for policy, decisions in consent["by_policy_version"].items():
        acc = decisions.get("accepted", 0)
        tot = acc + decisions.get("declined", 0)
        lines.append(f"  - policy v{policy}: accepted {_rate(acc, tot)}")
    lines += [
        f"- Sessions with ≥1 turn: {sessions}",
        f"- Turns: {metrics.get('turns', 0)} (per session: mean {_fmt(metrics.get('turns_per_session_mean'))}, median {_fmt(metrics.get('turns_per_session_median'))})",
        f"- Language split (turns): {metrics.get('language_turns') or 'n/a'}",
    ]
    if metrics["source"] == "events":
        lines += [
            f"- Booking widget shown (FINAL post-gate): {funnel['widget_shown_turns']} turns, {_rate(funnel['widget_shown_sessions'], sessions)} sessions",
            f"- Appointment requested (FINAL post-gate): {funnel['appointment_requested_turns']} turns, {_rate(funnel['appointment_requested_sessions'], sessions)} sessions",
            f"- Gate corrections: suppressed {funnel['gate_suppressed_turns']} (model wanted widget, gate said no), granted {funnel['gate_granted_turns']} (proactive)",
        ]
    else:
        lines += [
            f"- PRE-GATE widget-flag turns (model intent, NOT widgets shown): {funnel.get('pre_gate_widget_turns', 0)}",
            f"- PRE-GATE appointment-flag turns: {funnel.get('pre_gate_appointment_turns', 0)}",
            f"- Post-gate corrections: suppressed {funnel.get('gate_suppressed_turns', 0)}, proactive {funnel.get('gate_granted_turns', 0)}",
        ]
    lines += [
        f"- Sessions with handover requested: {_rate(funnel.get('handover_sessions', 0), sessions)}",
        f"- Programme distribution (turn mentions, final): {funnel.get('programme_turns') or 'n/a'}",
        f"- Suggested programme (latest per session): {funnel.get('suggested_program_sessions') or 'n/a'}",
        "- Note: actual Calendly bookings are NOT observable in this system.",
        "",
        "## 2. Answer Quality (offline rubric)",
        "",
    ]
    if rubric and rubric.get("sampled", 0) > 0:
        lines.append(
            f"- Sampled conversations: {rubric['sampled']} (judge model: {rubric.get('model', 'n/a')})"
        )
        for dim, agg in sorted((rubric.get("aggregates") or {}).items()):
            lines.append(
                f"- {dim}: mean {_fmt(agg.get('mean'))} / min {_fmt(agg.get('min'))} (0–10)"
            )
        flag_counts = rubric.get("flag_counts") or {}
        lines.append(f"- Flags raised: {flag_counts or 'none'}")
    else:
        lines.append(
            "- Not available (transcript storage disabled or no transcripts in window)."
        )
    lines += [
        "",
        "## 3. Risks & Reliability",
        "",
    ]
    if metrics["source"] == "events":
        lines += [
            f"- Agent invoke failures: {risks.get('agent_invoke_failed_turns', 0)}",
            f"- Streaming fallbacks (event flag): {risks.get('streaming_fallback_turns', 0)}",
            f"- Streaming fallbacks (logs.log I4 cross-check, MUST stay ~0): {metrics['i4_blocking_fallback_log_lines']}",
            f"- Empty-retrieval turns: {risks.get('retrieval_empty_turns', 0)}",
            f"- Scope redirects: {risks.get('scope_redirect_turns', 0)} (by type: {risks.get('scope_types') or 'none'})",
            f"- Invalid-input turns: {risks.get('invalid_input_turns', 0)}",
            f"- Max-turns endings: {risks.get('max_turns_endings', 0)}",
            f"- Exceptions: {risks.get('exception_turns', 0)}",
            f"- Turns slower than 15 s: {risks.get('slow_turns_over_15s', 0)}",
            f"- Consent declines: {declined}",
        ]
    else:
        lines += [
            f"- Streaming fallbacks (logs.log I4 cross-check, MUST stay ~0): {metrics['i4_blocking_fallback_log_lines']}",
            f"- Consent declines: {declined}",
            "- Further risk metrics require structured usage events (not present in window).",
        ]
    lines += [
        "",
        "## 4. Latency",
        "",
        f"- Total turn: p50 {_fmt(latency.get('total_s_p50'), ' s')}, p90 {_fmt(latency.get('total_s_p90'), ' s')}, p99 {_fmt(latency.get('total_s_p99'), ' s')}",
        f"- First token: p50 {_fmt(latency.get('first_token_s_p50'), ' s')}, p90 {_fmt(latency.get('first_token_s_p90'), ' s')}",
        f"- Preprocessing: p50 {_fmt(latency.get('preprocess_s_p50'), ' s')}",
        "",
        "## 5. Data Protection Status",
        "",
        f"- Transcript files written in window: {metrics.get('transcripts_in_window', 0)}"
        + (" (transcript storage appears DISABLED)" if metrics.get("transcripts_in_window", 0) == 0 else ""),
        "- Retention: usage events, transcripts and profiles are deleted after 30 days (host cron); reports contain aggregates only.",
        "- Wipe requests: per-session files absent for wiped sessions (not separately counted).",
        "",
        "## 6. Caveats",
        "",
    ]
    caveats = []
    if sessions == 0 and total_consent == 0:
        caveats.append("NO TRAFFIC in window — this report establishes no baseline.")
    elif sessions < LOW_TRAFFIC_SESSIONS:
        caveats.append(
            f"LOW TRAFFIC ({sessions} sessions < {LOW_TRAFFIC_SESSIONS}): percentage rates are not meaningful."
        )
    if metrics["source"] == "legacy":
        caveats.append(
            "Legacy parsing: booking metrics are PRE-GATE model intent, and logs.log has no session ids."
        )
    if not caveats:
        caveats.append("None.")
    lines += [f"- {c}" for c in caveats]
    lines.append("")
    return "\n".join(lines)


# ------------------------------------ CLI -------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--out", help="write markdown report to this path (default: stdout)")
    parser.add_argument("--json", dest="json_out", help="also mirror metrics as JSON")
    parser.add_argument(
        "--rubric-scores",
        help="rubric_scores.json from scripts/rubric_judge.py (aggregates are ingested)",
    )
    args = parser.parse_args(argv)

    metrics = collect_metrics(args.logs_dir, args.window_days)

    rubric = None
    if args.rubric_scores and Path(args.rubric_scores).exists():
        try:
            rubric = json.loads(Path(args.rubric_scores).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("WARNING: rubric scores file is not valid JSON — skipping", file=sys.stderr)

    markdown = render_markdown(metrics, rubric)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"Report written to {out_path}")
    else:
        print(markdown)

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        if rubric:
            metrics = {**metrics, "rubric": {k: v for k, v in rubric.items() if k != "sessions"}}
        json_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
