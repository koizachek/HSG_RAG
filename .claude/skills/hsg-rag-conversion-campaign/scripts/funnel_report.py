#!/usr/bin/env python3
"""Conversion funnel report over the HSG_RAG logs directory.

Usage:
    python3 funnel_report.py /opt/hsg-rag/logs          # on the prod host
    python3 funnel_report.py ./logs                     # over an rsynced copy

Reads (verified layout as of 2026-07-07):
  <logs>/consent/<session_id>.jsonl        one JSON object per consent decision
  <logs>/user_profiles/profile_<session_id>_<YYYYmmdd_HHMMSS>.json  snapshots
  <logs>/logs.log                          '(%Y.%m.%d %H:%M:%S) name\t LEVEL: msg'

Outputs aggregate counts/rates ONLY (GDPR: no names, no query text). Per-session
joins use consent + profile files (they carry session_id); logs.log has no
session id and is used for aggregate widget/appointment counts only.

PRE-GATE METRIC CAVEAT: the 'Show Booking Widget: True' / 'Appointment
Requested: True' lines counted here are the model's RAW flags, logged at
src/rag/agent_chain.py:773-775 BEFORE the post-processing gate at
agent_chain.py:833-872 (commit 55fa853). The gate can suppress booking state,
grant it proactively, or force the widget on a text commitment — so stages
3a/3b measure PRE-GATE MODEL INTENT, not widgets actually shown. Final flag
values are not logged unconditionally (verified 2026-07-08); the two
conditional post-gate lines ('Proactive booking offer triggered',
'Suppressed booking state') are counted separately as correction signals.
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

WINDOW_DAYS = 7  # compare equal-length windows before/after a change


def read_jsonl_objects(path: Path):
    """Files contain pretty-printed JSON objects back to back; split on '}\n{'."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    chunks = re.split(r"}\s*{", text)
    objs = []
    for i, chunk in enumerate(chunks):
        if not chunk.startswith("{"):
            chunk = "{" + chunk
        if not chunk.rstrip().endswith("}"):
            chunk = chunk + "}"
        try:
            objs.append(json.loads(chunk))
        except json.JSONDecodeError:
            pass
    return objs


def main(logs_dir: str) -> int:
    root = Path(logs_dir)
    cutoff = datetime.now() - timedelta(days=WINDOW_DAYS)

    # --- Stage 1: consent ---
    consent = Counter()
    sessions_accepted = set()
    for f in sorted((root / "consent").glob("*.jsonl")):
        for obj in read_jsonl_objects(f):
            ts = obj.get("timestamp", "")
            try:
                when = datetime.fromisoformat(ts).replace(tzinfo=None)
            except ValueError:
                continue
            if when < cutoff:
                continue
            consent[obj.get("decision", "unknown")] += 1
            if obj.get("decision") == "accepted":
                sessions_accepted.add(obj.get("session_id"))

    # --- Stage 2/3 per session: profiles (handover, programme) ---
    sessions_with_profile = set()
    sessions_handover = set()
    programme_dist = Counter()
    latest_by_session = {}
    for f in (root / "user_profiles").glob("profile_*.json"):
        m = re.match(r"profile_(.+)_(\d{8}_\d{6})\.json$", f.name)
        if not m:
            continue
        sid, stamp = m.group(1), m.group(2)
        when = datetime.strptime(stamp, "%Y%m%d_%H%M%S")
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
            programme_dist[prof["suggested_program"]] += 1

    # --- Aggregates from logs.log (no session id available) ---
    line_re = re.compile(r"^\((\d{4}\.\d{2}\.\d{2}) \d{2}:\d{2}:\d{2}\)")
    counters = Counter()
    log_file = root / "logs.log"
    if log_file.exists():
        with log_file.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = line_re.match(line)
                if m:
                    day = datetime.strptime(m.group(1), "%Y.%m.%d")
                    if day < cutoff:
                        continue
                if "Show Booking Widget: True" in line:
                    counters["widget_true_turns"] += 1
                elif "Appointment Requested: True" in line:
                    counters["appointment_true_turns"] += 1
                elif "Proactive booking offer triggered" in line:
                    counters["proactive_offer_turns"] += 1
                elif "Suppressed booking state" in line:
                    counters["suppressed_booking_turns"] += 1
                elif "Processing user query:" in line:
                    counters["user_turns"] += 1

    # --- Report (aggregates only) ---
    acc, dec = consent.get("accepted", 0), consent.get("declined", 0)
    total_consent = acc + dec

    def rate(n, d):
        return f"{n}/{d} ({100 * n / d:.0f}%)" if d else f"{n}/0 (n/a)"

    print(f"Funnel report — last {WINDOW_DAYS} days, logs dir: {root}")
    print("NOTE: 3a/3b count RAW model flags (agent_chain.py:773-775) logged BEFORE the")
    print("      post-processing gate (agent_chain.py:833-872) — PRE-GATE MODEL INTENT,")
    print("      not widgets actually shown. 3c/3d are the post-gate correction signals.")
    print(f"1. Consent decisions : {total_consent}  accepted {rate(acc, total_consent)}")
    print(f"2. Active sessions   : {len(sessions_with_profile)} with >=1 profile snapshot")
    print(f"3a. Widget-flag turns (pre-gate model intent, aggr.)      : {counters['widget_true_turns']}")
    print(f"3b. Appointment-flag turns (pre-gate model intent, aggr.) : {counters['appointment_true_turns']}")
    print(f"3c. Post-gate: proactive booking offers granted           : {counters['proactive_offer_turns']}")
    print(f"3d. Post-gate: booking state suppressed by the gate       : {counters['suppressed_booking_turns']}")
    print(f"3e. Sessions with handover=true         : {rate(len(sessions_handover), len(sessions_with_profile))}")
    print(f"    User turns total (aggregate)        : {counters['user_turns']}")
    print(f"    Suggested-programme distribution    : {dict(programme_dist) or '(none)'}")
    print("4. Actual Calendly bookings: NOT observable here — ask advisors (stakeholder-comms).")
    if total_consent == 0 and not sessions_with_profile:
        print("\nWARNING: no traffic in window — baseline not establishable (GATE 0 fails).")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
