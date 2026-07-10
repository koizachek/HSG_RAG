"""
Tests for scripts/usage_report.py

Contract under test:
- structured usage events are the preferred source (final post-gate flags)
- legacy fallback (consent + profiles + logs.log) works with pre-gate caveat
- the markdown report contains NO session ids (anonymity)
- rubric aggregates are ingested; per-session scores never reach the outputs
- empty logs dir produces a valid "no traffic" report and exit code 0
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# Import the script as a module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import usage_report


SESSION_A = "aaaaaaaa-1111-2222-3333-444444444444"
SESSION_B = "bbbbbbbb-5555-6666-7777-888888888888"


def _event(session_id, turn_index, **overrides):
    event = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "turn_index": turn_index,
        "language": "de",
        "outcome": "answered",
        "scope_type": None,
        "query_len_chars": 42,
        "pre_gate": {
            "appointment_requested": False,
            "show_booking_widget": False,
            "relevant_programs": [],
        },
        "final": {
            "appointment_requested": False,
            "show_booking_widget": False,
            "relevant_programs": [],
            "confidence_fallback": False,
            "max_turns_reached": False,
        },
        "suggested_program": None,
        "handover_requested": None,
        "streaming_fallback": False,
        "agent_invoke_failed": False,
        "retrieval_calls": 1,
        "retrieval_empty": False,
        "timing": {"total_s": 4.0, "preprocess_s": 0.01, "first_token_s": 2.0},
    }
    event.update(overrides)
    return event


def build_fixture_logs(tmp_path):
    logs = tmp_path / "logs"
    (logs / "usage").mkdir(parents=True)
    (logs / "consent").mkdir()

    now = datetime.now(timezone.utc)
    for sid, decision in [(SESSION_A, "accepted"), (SESSION_B, "accepted")]:
        (logs / "consent" / f"{sid}.jsonl").write_text(
            json.dumps(
                {
                    "session_id": sid,
                    "decision": decision,
                    "timestamp": now.isoformat(),
                    "policy_version": "1.0",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    events_a = [
        _event(SESSION_A, 1),
        _event(
            SESSION_A,
            2,
            outcome="answered",
            suggested_program="emba",
            final={
                "appointment_requested": True,
                "show_booking_widget": True,
                "relevant_programs": ["emba"],
                "confidence_fallback": False,
                "max_turns_reached": False,
            },
            pre_gate={
                "appointment_requested": False,
                "show_booking_widget": False,
                "relevant_programs": ["emba"],
            },
        ),
    ]
    events_b = [
        _event(SESSION_B, 1, outcome="scope_redirect", scope_type="competitor",
               pre_gate=None, timing={"total_s": 0.1, "preprocess_s": 0.05,
                                      "first_token_s": None}),
        _event(SESSION_B, 2, streaming_fallback=True, retrieval_empty=True),
    ]
    for sid, events in [(SESSION_A, events_a), (SESSION_B, events_b)]:
        (logs / "usage" / f"usage_{sid}.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )
    return logs


class TestEventMetrics:

    def test_metrics_from_events(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        metrics = usage_report.collect_metrics(str(logs), window_days=7)

        assert metrics["source"] == "events"
        assert metrics["sessions"] == 2
        assert metrics["turns"] == 4
        assert metrics["consent"]["accepted"] == 2
        assert metrics["funnel"]["widget_shown_turns"] == 1
        assert metrics["funnel"]["widget_shown_sessions"] == 1
        assert metrics["funnel"]["gate_granted_turns"] == 1  # pre False -> final True
        assert metrics["funnel"]["suggested_program_sessions"] == {"emba": 1}
        assert metrics["risks"]["streaming_fallback_turns"] == 1
        assert metrics["risks"]["retrieval_empty_turns"] == 1
        assert metrics["risks"]["scope_types"] == {"competitor": 1}
        assert metrics["latency"]["total_s_p50"] is not None

    def test_old_events_outside_window_excluded(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        old = _event(
            SESSION_A,
            99,
            timestamp=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        )
        with (logs / "usage" / f"usage_{SESSION_A}.jsonl").open("a") as f:
            f.write(json.dumps(old) + "\n")

        metrics = usage_report.collect_metrics(str(logs), window_days=7)
        assert metrics["turns"] == 4


class TestMarkdownReport:

    def test_report_contains_no_session_ids(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        metrics = usage_report.collect_metrics(str(logs), window_days=7)
        markdown = usage_report.render_markdown(metrics)

        assert SESSION_A not in markdown
        assert SESSION_B not in markdown
        assert "aaaaaaaa" not in markdown

    def test_report_sections_present(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        metrics = usage_report.collect_metrics(str(logs), window_days=7)
        markdown = usage_report.render_markdown(metrics)

        for heading in [
            "## 1. Traffic & Funnel",
            "## 2. Answer Quality",
            "## 3. Risks & Reliability",
            "## 4. Latency",
            "## 5. Data Protection Status",
            "## 6. Caveats",
        ]:
            assert heading in markdown

    def test_low_traffic_caveat(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        metrics = usage_report.collect_metrics(str(logs), window_days=7)
        markdown = usage_report.render_markdown(metrics)
        assert "LOW TRAFFIC" in markdown  # 2 sessions < 5

    def test_rubric_aggregates_rendered_without_sessions(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        metrics = usage_report.collect_metrics(str(logs), window_days=7)
        rubric = {
            "sampled": 3,
            "model": "openai/gpt-4o-mini",
            "aggregates": {"helpfulness": {"mean": 8.7, "min": 8.0}},
            "flag_counts": {"missed_booking_opportunity": 1},
            "sessions": [{"session_id": SESSION_A, "scores": {}}],
        }
        markdown = usage_report.render_markdown(metrics, rubric)

        assert "helpfulness: mean 8.7" in markdown
        assert "missed_booking_opportunity" in markdown
        assert SESSION_A not in markdown


class TestLegacyFallback:

    def test_legacy_metrics_without_events(self, tmp_path):
        logs = tmp_path / "logs"
        (logs / "user_profiles").mkdir(parents=True)
        (logs / "consent").mkdir()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        (logs / "user_profiles" / f"profile_{SESSION_A}_{stamp}.json").write_text(
            json.dumps({"handover": True, "suggested_program": "iemba"}),
            encoding="utf-8",
        )
        day = datetime.now(timezone.utc).strftime("%Y.%m.%d")
        (logs / "logs.log").write_text(
            f"({day} 10:00:00) agent_chain\t INFO: Show Booking Widget: True\n"
            f"({day} 10:00:01) chatbot_app\t INFO: Processing user query: <redacted>\n",
            encoding="utf-8",
        )

        metrics = usage_report.collect_metrics(str(logs), window_days=7)
        assert metrics["source"] == "legacy"
        assert metrics["funnel"]["pre_gate_widget_turns"] == 1
        assert metrics["funnel"]["handover_sessions"] == 1
        assert metrics["funnel"]["suggested_program_sessions"] == {"iemba": 1}

        markdown = usage_report.render_markdown(metrics)
        assert "PRE-GATE" in markdown
        assert SESSION_A not in markdown


class TestCli:

    def test_empty_logs_dir_first_run_safe(self, tmp_path, capsys):
        logs = tmp_path / "logs"
        logs.mkdir()
        out = tmp_path / "report.md"

        exit_code = usage_report.main(
            ["--logs-dir", str(logs), "--out", str(out)]
        )
        assert exit_code == 0
        assert "NO TRAFFIC" in out.read_text(encoding="utf-8")

    def test_json_mirror_written(self, tmp_path):
        logs = build_fixture_logs(tmp_path)
        out = tmp_path / "report.md"
        json_out = tmp_path / "report.json"

        exit_code = usage_report.main(
            ["--logs-dir", str(logs), "--out", str(out), "--json", str(json_out)]
        )
        assert exit_code == 0
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["sessions"] == 2
