"""
Chain-level tests for the per-turn usage-event instrumentation
(src/rag/agent_chain.py: query() wrapper, _emit_turn_event, outcome tags).

Contract under test:
- EVERY turn (early return, answered, exception) emits exactly one event
- the event carries the FINAL post-gate flags and the right outcome
- error/fallback markers are set by the failing code paths
- events contain NO free text (redaction guard)
"""
import json
import os
import sys

import pytest

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rag import agent_chain as agent_chain_module
from src.rag.utilclasses import LeadAgentQueryResponse


class DummyWeaviateService:
    pass


def make_chain(monkeypatch, session_id="usage-test-session", language="en"):
    monkeypatch.setattr(agent_chain_module, "WeaviateService", DummyWeaviateService)
    monkeypatch.setattr(
        agent_chain_module.ExecutiveAgentChain, "_init_agents", lambda self: ({}, {})
    )
    chain = agent_chain_module.ExecutiveAgentChain(language=language, session_id=session_id)
    # Keep preprocessing deterministic and offline
    monkeypatch.setattr(
        chain._language_detector, "detect_explicit_switch_request", lambda q: None
    )
    monkeypatch.setattr(
        chain._language_detector, "is_language_neutral_input", lambda q: True
    )
    monkeypatch.setattr(chain._scope_guardian, "check_scope", lambda q, lang: "on_topic")
    return chain


def read_events(tmp_path, session_id="usage-test-session"):
    log_path = tmp_path / "logs" / "usage" / f"usage_{session_id}.jsonl"
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]


def answered_response(**overrides):
    defaults = dict(
        response="Here is your answer.",
        language="en",
        processed_query="q",
        appointment_requested=True,
        show_booking_widget=True,
        relevant_programs=["emba"],
    )
    defaults.update(overrides)
    return LeadAgentQueryResponse(**defaults)


class TestTurnEventEmission:

    def test_answered_turn_emits_event_with_final_flags(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)
        monkeypatch.setattr(
            chain, "_query_lead", lambda q, on_delta=None: answered_response()
        )

        chain.query("Tell me about the EMBA")

        events = read_events(tmp_path)
        assert len(events) == 1
        event = events[0]
        assert event["outcome"] == "answered"
        assert event["turn_index"] == 1
        assert event["final"] == {
            "appointment_requested": True,
            "show_booking_widget": True,
            "relevant_programs": ["emba"],
            "confidence_fallback": False,
            "max_turns_reached": False,
        }
        assert event["language"] == "en"
        assert event["timing"]["total_s"] is not None

    def test_event_contains_no_free_text(self, monkeypatch, tmp_path):
        """Redaction guard: neither the user query nor the answer text may
        appear anywhere in the usage event file."""
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)
        marker_answer = "ANSWER_MARKER_c3d4"
        monkeypatch.setattr(
            chain,
            "_query_lead",
            lambda q, on_delta=None: answered_response(response=marker_answer),
        )

        marker_query = "SECRET_MARKER_a1b2 my name is Jane Doe"
        chain.query(marker_query)

        raw = (
            tmp_path / "logs" / "usage" / "usage_usage-test-session.jsonl"
        ).read_text(encoding="utf-8")
        assert "SECRET_MARKER_a1b2" not in raw
        assert "Jane Doe" not in raw
        assert marker_answer not in raw
        event = json.loads(raw)
        assert event["query_len_chars"] == len(marker_query)

    def test_invalid_input_turn(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)
        monkeypatch.setattr(
            chain._input_handler, "process_input", lambda q, h: (q, False)
        )

        chain.query("!!!")

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["outcome"] == "invalid_input"
        assert events[0]["final"] is not None  # early returns still carry final flags

    def test_scope_redirect_turn(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)
        monkeypatch.setattr(
            chain._scope_guardian, "check_scope", lambda q, lang: "competitor"
        )
        monkeypatch.setattr(
            chain._scope_guardian,
            "should_escalate",
            lambda q, scope_type, count: (False, None),
        )
        monkeypatch.setattr(
            chain._scope_guardian,
            "get_redirect_message",
            lambda scope_type, lang: "redirect message",
        )

        chain.query("What about competitor X?")

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["outcome"] == "scope_redirect"
        assert events[0]["scope_type"] == "competitor"

    def test_max_turns_turn(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)
        monkeypatch.setattr(
            agent_chain_module.config.convstate, "MAX_CONVERSATION_TURNS", 0
        )

        chain.query("one question too many")

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["outcome"] == "max_turns"
        assert events[0]["final"]["max_turns_reached"] is True

    def test_exception_turn_still_emits_event(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)

        def boom(q, on_delta=None):
            raise RuntimeError("pipeline blew up")

        monkeypatch.setattr(chain, "_query_lead", boom)

        with pytest.raises(RuntimeError):
            chain.query("trigger the exception")

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["outcome"] == "exception"
        assert events[0]["final"] is None

    def test_turn_index_increments_and_flags_reset(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)

        def lead_with_fallback_flag(q, on_delta=None):
            chain._tag_turn("streaming_fallback", True)
            return answered_response()

        monkeypatch.setattr(chain, "_query_lead", lead_with_fallback_flag)
        chain.query("first turn")

        monkeypatch.setattr(
            chain, "_query_lead", lambda q, on_delta=None: answered_response()
        )
        chain.query("second turn")

        events = read_events(tmp_path)
        assert [e["turn_index"] for e in events] == [1, 2]
        assert events[0]["streaming_fallback"] is True
        assert events[1]["streaming_fallback"] is False  # flags reset per turn

    def test_pre_gate_flags_recorded(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        chain = make_chain(monkeypatch)

        def lead_with_pre_gate(q, on_delta=None):
            chain._tag_turn(
                "pre_gate",
                {
                    "appointment_requested": True,
                    "show_booking_widget": True,
                    "relevant_programs": ["emba"],
                },
            )
            # gate suppressed the flags in the final response
            return answered_response(
                appointment_requested=False, show_booking_widget=False
            )

        monkeypatch.setattr(chain, "_query_lead", lead_with_pre_gate)
        chain.query("am I ready?")

        event = read_events(tmp_path)[0]
        assert event["pre_gate"]["show_booking_widget"] is True
        assert event["final"]["show_booking_widget"] is False


class TestErrorMarkers:

    def test_streaming_failure_sets_fallback_flag(self, monkeypatch):
        chain = make_chain(monkeypatch)
        chain._begin_turn_telemetry()

        class FailingAgent:
            name = "lead"

            def stream(self, *args, **kwargs):
                raise RuntimeError("stream broke")

        result = chain._invoke_streaming(
            FailingAgent(), [], {"configurable": {}}, on_delta=lambda d: None
        )
        assert result is None
        assert chain._turn_flags["streaming_fallback"] is True

    def test_agent_invoke_failure_sets_error_markers(self, monkeypatch):
        chain = make_chain(monkeypatch)
        chain._begin_turn_telemetry()

        class FailingAgent:
            name = "lead"

            def invoke(self, *args, **kwargs):
                raise RuntimeError("invoke broke")

        response = chain._query(agent=FailingAgent(), messages=[])
        assert chain._turn_flags["agent_invoke_failed"] is True
        assert chain._turn_flags["outcome"] == "agent_error"
        assert response.response  # the graceful exception message

    def test_helpers_are_safe_without_begin_turn(self, monkeypatch):
        """Tests that bypass query() (no _begin_turn_telemetry) must not break."""
        chain = make_chain(monkeypatch)
        chain._turn_flags = None
        chain._tag_turn("outcome", "answered")  # must not raise
        chain._bump_turn("retrieval_calls")  # must not raise
